import asyncio
import hashlib
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
from zoneinfo import ZoneInfo

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from telegram import InputFile
from telegram.error import TelegramError, TimedOut

from . import bot as bot_module
from . import config, db
from .security import verify_init_data

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ays.main")

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    application = bot_module.build_application()
    app.state.bot_application = application
    app.state.scheduled_job = None
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    log.info("Telegram bot polling started")
    if config.PUBLIC_URL:
        log.info("Mini App URL to register with BotFather: %s", config.PUBLIC_URL)
    else:
        log.warning("PUBLIC_URL not set in .env — set it to your https tunnel URL")
    yield
    if app.state.scheduled_job is not None:
        app.state.scheduled_job["task"].cancel()
    await application.updater.stop()
    await application.stop()
    await application.shutdown()


app = FastAPI(lifespan=lifespan)


# Telegram's in-app browsers cache Mini App assets hard, and there's no way to
# force-refresh from a phone. That produced a genuinely confusing bug: a new
# button appeared on iOS but not Android, because Android was still running a
# stale boss.js. These files are a few KB, so always serve them fresh rather
# than ever debug that again.
NO_STORE = {"Cache-Control": "no-store, must-revalidate"}


class NoCacheStaticFiles(StaticFiles):
    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers.update(NO_STORE)
        return response


app.mount("/static", NoCacheStaticFiles(directory=WEB_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(WEB_DIR / "index.html", headers=NO_STORE)


@app.get("/boss")
async def boss_page():
    return FileResponse(WEB_DIR / "boss.html", headers=NO_STORE)


@app.get("/archive")
async def archive_page():
    return FileResponse(WEB_DIR / "archive.html", headers=NO_STORE)


class ChecklistRequest(BaseModel):
    init_data: str


def _authenticate(init_data: str):
    user = verify_init_data(init_data)
    if user is None:
        raise HTTPException(status_code=401, detail="Could not verify Telegram identity")
    if user["id"] not in config.ALLOWED_IDS:
        raise HTTPException(
            status_code=403,
            detail=f"You're not registered yet. Your Telegram ID is {user['id']}. "
            "Ask the boss to add you.",
        )
    if config.MAINTENANCE_MODE and user["id"] not in config.BOSS_IDS:
        raise HTTPException(
            status_code=503,
            detail="The work plan is being updated. Please check back in a few minutes.",
        )
    return user


def _authenticate_boss(init_data: str):
    user = _authenticate(init_data)
    if user["id"] not in config.BOSS_IDS:
        raise HTTPException(status_code=403, detail="Boss only")
    return user


def _tz() -> ZoneInfo:
    return ZoneInfo(config.TIMEZONE)


def _plan_date_str():
    sent_at = db.get_plan_sent_at()
    if not sent_at:
        return None
    return datetime.fromisoformat(sent_at).astimezone(_tz()).strftime("%d/%m/%Y")


class WhoAmIRequest(BaseModel):
    init_data: str


@app.post("/api/whoami")
async def api_whoami(req: WhoAmIRequest):
    """Lets the checklist page send bosses straight to the library — Telegram's
    menu button is a single fixed URL for the whole bot, so the routing has to
    happen after we know who opened it."""
    user = _authenticate(req.init_data)
    return {"is_boss": user["id"] in config.BOSS_IDS}


@app.post("/api/checklist")
async def api_checklist(req: ChecklistRequest):
    _authenticate(req.init_data)
    items, all_done = db.get_checklist()
    return {
        "items": items,
        "all_done": all_done,
        "plan_date": _plan_date_str(),
    }


# Telegram file_ids are immutable, so a fetched file never needs refetching.
# Cached on disk (survives restarts) with a size cap so it can't grow without
# bound; the oldest files are evicted first.
MEDIA_CACHE_DIR = config.MEDIA_CACHE_DIR
MEDIA_CACHE_MAX_BYTES = int(os.environ.get("MEDIA_CACHE_MAX_MB", "400")) * 1024 * 1024
_MEDIA_CACHE_HEADERS = {"Cache-Control": "private, max-age=31536000, immutable"}


def _cache_paths(file_id: str):
    key = hashlib.sha256(file_id.encode()).hexdigest()
    return MEDIA_CACHE_DIR / f"{key}.bin", MEDIA_CACHE_DIR / f"{key}.type"


def _cache_lookup(file_id: str):
    blob_path, type_path = _cache_paths(file_id)
    try:
        data = blob_path.read_bytes()
        content_type = type_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    # Refresh mtime so eviction treats recently-viewed files as hot.
    try:
        os.utime(blob_path, None)
    except OSError:
        pass
    return data, content_type


def _cache_store(file_id: str, data: bytes, content_type: str) -> None:
    blob_path, type_path = _cache_paths(file_id)
    try:
        MEDIA_CACHE_DIR.mkdir(exist_ok=True)
        blob_path.write_bytes(data)
        type_path.write_text(content_type, encoding="utf-8")
        _cache_evict()
    except OSError:
        log.warning("Could not write media cache entry", exc_info=True)


def _cache_evict() -> None:
    blobs = sorted(MEDIA_CACHE_DIR.glob("*.bin"), key=lambda p: p.stat().st_mtime)
    total = sum(p.stat().st_size for p in blobs)
    while total > MEDIA_CACHE_MAX_BYTES and blobs:
        oldest = blobs.pop(0)
        total -= oldest.stat().st_size
        oldest.unlink(missing_ok=True)
        oldest.with_suffix(".type").unlink(missing_ok=True)


def _extract_file_id(msg):
    """Telegram decides for itself how to classify an upload, so read the
    file_id off whichever attribute it actually populated. Only photo/video/
    document are possible here: send_photo can only yield a photo, and
    send_video/send_document (the only two calls we ever make for video) can
    only yield a video or a document."""
    for attr in ("video", "document"):
        media = getattr(msg, attr, None)
        if media is not None:
            return media.file_id
    if msg.photo:
        return msg.photo[-1].file_id
    return None


@app.post("/api/attach")
async def api_attach(
    request: Request,
    init_data: str = Form(...),
    item_id: int = Form(...),
    file: UploadFile = File(...),
):
    user = _authenticate(init_data)

    if not db.is_active_and_pending(item_id):
        raise HTTPException(status_code=400, detail="Item not found or already finished")

    item_text, section, villa = db.get_item_text(item_id)
    if item_text is None:
        raise HTTPException(status_code=400, detail="Item not found")

    media_type = "video" if (file.content_type or "").startswith("video/") else "photo"
    file_bytes = await file.read()

    user_name = user.get("first_name") or user.get("username") or str(user["id"])
    if user.get("last_name"):
        user_name = f"{user_name} {user['last_name']}"
    caption = f"Villa {villa} — {section}: {item_text}\nFinished by {user_name}"

    bot = request.app.state.bot_application.bot
    try:
        if media_type == "photo":
            msg = await bot.send_photo(
                config.STORAGE_CHAT_ID,
                InputFile(file_bytes, filename=file.filename),
                caption=caption,
            )
            media_file_id = _extract_file_id(msg)
        else:
            # An in-app recording may be a format send_video won't take. That
            # shows up two ways: an outright error, or — less obviously —
            # Telegram accepting the call but reclassifying the file, leaving
            # msg.video empty. Handle both, then fall back to send_document,
            # which accepts anything and still yields a usable file_id.
            media_file_id = None
            try:
                msg = await bot.send_video(
                    config.STORAGE_CHAT_ID,
                    InputFile(file_bytes, filename=file.filename),
                    caption=caption,
                )
                media_file_id = _extract_file_id(msg)
            except TimedOut:
                # Never retry on a timeout: the upload has very likely landed
                # on Telegram's side already, and re-sending just puts a second
                # copy of the same video in the channel.
                log.exception("send_video timed out")
                raise HTTPException(
                    status_code=504,
                    detail="That took too long to send. Check the channel before retrying.",
                )
            except TelegramError:
                log.warning("send_video rejected %s", file.content_type)

            if media_file_id is None:
                log.warning("storing %s as a document instead", file.content_type)
                msg = await bot.send_document(
                    config.STORAGE_CHAT_ID,
                    InputFile(file_bytes, filename=file.filename),
                    caption=caption,
                )
                media_file_id = _extract_file_id(msg)

        if media_file_id is None:
            raise HTTPException(status_code=502, detail="Could not save that. Try again.")
    except TelegramError:
        log.exception("Failed to store media")
        raise HTTPException(status_code=502, detail="Could not save that. Try again.")

    db.mark_done(item_id, user["id"], user_name, media_file_id, media_type)
    items, all_done = db.get_checklist()
    if all_done:
        date_str = _plan_date_str() or datetime.now(_tz()).strftime("%d/%m/%Y")
        await bot_module.notify_all_done(bot, date_str)
    return {
        "items": items,
        "all_done": all_done,
        "plan_date": _plan_date_str(),
    }


class MediaRequest(BaseModel):
    init_data: str
    item_id: int


@app.post("/api/media")
async def api_media(req: MediaRequest, request: Request):
    _authenticate(req.init_data)

    media_file_id, media_type = db.get_media(req.item_id)
    if media_file_id is None:
        raise HTTPException(status_code=404, detail="No media for this item")

    # Media in Telegram is immutable per file_id, so anything fetched once can
    # be cached forever. Without this, every tap on a 📷/🎬 icon re-downloads
    # the whole file from Telegram, which is slow for videos in particular.
    cached = _cache_lookup(media_file_id)
    if cached is not None:
        data, content_type = cached
        return Response(content=data, media_type=content_type, headers=_MEDIA_CACHE_HEADERS)

    bot = request.app.state.bot_application.bot
    try:
        tg_file = await bot.get_file(media_file_id)
        data = await tg_file.download_as_bytearray()
    except TelegramError:
        log.exception("Failed to fetch media from Telegram")
        raise HTTPException(status_code=502, detail="Could not load the media. Try again.")

    # Telegram keeps the original extension in file_path, which is the only
    # record of the real format — in-app recordings may be WebM rather than
    # MP4, and serving those as video/mp4 makes them fail to play.
    ext = Path(tg_file.file_path or "").suffix.lower()
    by_ext = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mov": "video/quicktime",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
    }
    content_type = by_ext.get(ext) or ("video/mp4" if media_type == "video" else "image/jpeg")
    data = bytes(data)
    _cache_store(media_file_id, data, content_type)
    return Response(content=data, media_type=content_type, headers=_MEDIA_CACHE_HEADERS)


class BossRequest(BaseModel):
    init_data: str


class AddItemRequest(BaseModel):
    init_data: str
    villa: str
    section: str
    text: str


class RemoveItemRequest(BaseModel):
    init_data: str
    item_id: int


class SendPlanRequest(BaseModel):
    init_data: str
    item_ids: List[int]
    send_at: Optional[str] = None  # "HH:MM" 24h, in TIMEZONE; omit/None = send now


class CancelScheduleRequest(BaseModel):
    init_data: str


def _schedule_info(app: FastAPI):
    job = app.state.scheduled_job
    if job is None:
        return None
    target: datetime = job["target"]
    return {"time": target.strftime("%H:%M"), "date": target.strftime("%d/%m/%Y")}


def _boss_state(app: FastAPI):
    return {
        "library": db.list_library(),
        "pending_schedule": _schedule_info(app),
        "plan_date": _plan_date_str(),
    }


def _plan_already_sent_today(tz) -> bool:
    sent_at = db.get_plan_sent_at()
    if not sent_at:
        return False
    return datetime.fromisoformat(sent_at).astimezone(tz).date() == datetime.now(tz).date()


async def _fire_plan(app: FastAPI, item_ids: List[int]) -> None:
    tz = _tz()
    if _plan_already_sent_today(tz):
        # Same-day re-send: update the live plan in place instead of
        # starting a new generation, so finished items (tick, photo, who)
        # aren't wiped by a mid-day tweak.
        db.update_plan(item_ids)
    else:
        db.send_plan(item_ids)
    date_str = datetime.now(tz).strftime("%d/%m/%Y")
    bot = app.state.bot_application.bot
    await bot_module.notify_crew(bot, date_str)
    await bot_module.notify_boss_sent(bot, date_str)


async def _scheduled_send(app: FastAPI, item_ids: List[int], target: datetime) -> None:
    delay = (target - datetime.now(target.tzinfo)).total_seconds()
    if delay > 0:
        await asyncio.sleep(delay)
    await _fire_plan(app, item_ids)
    app.state.scheduled_job = None


def _cancel_pending(app: FastAPI) -> None:
    job = app.state.scheduled_job
    if job is not None:
        job["task"].cancel()
        app.state.scheduled_job = None


@app.post("/api/boss/library")
async def api_boss_library(req: BossRequest, request: Request):
    _authenticate_boss(req.init_data)
    return _boss_state(request.app)


@app.post("/api/boss/library/add")
async def api_boss_library_add(req: AddItemRequest, request: Request):
    _authenticate_boss(req.init_data)
    text = req.text.strip()
    section = req.section.strip() or "General"
    villa = req.villa.strip() or db.DEFAULT_VILLA
    if not text:
        raise HTTPException(status_code=400, detail="Item text can't be empty")
    new_id = db.add_library_item(villa, section, text)
    return {**_boss_state(request.app), "added_id": new_id}


@app.post("/api/boss/library/remove")
async def api_boss_library_remove(req: RemoveItemRequest, request: Request):
    _authenticate_boss(req.init_data)
    ok, error = db.remove_library_item(req.item_id)
    if not ok:
        raise HTTPException(status_code=400, detail=error)
    return _boss_state(request.app)


@app.post("/api/boss/send-plan")
async def api_boss_send_plan(req: SendPlanRequest, request: Request):
    # Empty item_ids is valid: on a same-day re-send it means "clear every
    # unfinished task" (finished ones are untouched regardless — see
    # db.update_plan); on a fresh send it means "send an empty checklist",
    # which is an unusual choice but the boss's to make.
    _authenticate_boss(req.init_data)

    app = request.app
    _cancel_pending(app)

    if not req.send_at:
        await _fire_plan(app, req.item_ids)
        return _boss_state(app)

    try:
        target_time = datetime.strptime(req.send_at, "%H:%M").time()
    except ValueError:
        raise HTTPException(status_code=400, detail="send_at must be HH:MM")

    tz = _tz()
    now = datetime.now(tz)
    target = datetime.combine(now.date(), target_time, tzinfo=tz)
    if target <= now:
        target += timedelta(days=1)

    task = asyncio.create_task(_scheduled_send(app, req.item_ids, target))
    app.state.scheduled_job = {"task": task, "target": target}
    return _boss_state(app)


@app.post("/api/boss/cancel-schedule")
async def api_boss_cancel_schedule(req: CancelScheduleRequest, request: Request):
    _authenticate_boss(req.init_data)
    _cancel_pending(request.app)
    return _boss_state(request.app)


class HistoryPlanRequest(BaseModel):
    init_data: str
    plan_id: int


@app.post("/api/boss/history")
async def api_boss_history(req: BossRequest):
    _authenticate_boss(req.init_data)
    tz = _tz()
    plans = db.list_plans()
    for p in plans:
        dt = datetime.fromisoformat(p["sent_at"]).astimezone(tz)
        p["date"] = dt.strftime("%d/%m/%Y")
        p["time"] = dt.strftime("%H:%M")
    return {"plans": plans}


@app.post("/api/boss/history/plan")
async def api_boss_history_plan(req: HistoryPlanRequest):
    _authenticate_boss(req.init_data)
    items = db.get_plan_items(req.plan_id)
    return {"items": items}
