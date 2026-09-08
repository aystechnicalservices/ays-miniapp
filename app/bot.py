import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from . import config, db, gemini

log = logging.getLogger("ays.bot")


def build_application() -> Application:
    # Defaults are ~5s, which is far too short for a video upload: the send
    # completes on Telegram's side but times out here, so the file lands in
    # the channel while the app reports failure (and then re-uploads via the
    # document fallback). Media transfers get generous timeouts instead.
    application = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .write_timeout(300)
        .read_timeout(300)
        .connect_timeout(30)
        .pool_timeout(30)
        .media_write_timeout(300)
        .build()
    )
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("menu", start_handler))
    application.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO, stray_media_handler))
    return application


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in config.ALLOWED_IDS:
        await update.message.reply_text(
            f"You're not registered for this yet. Your Telegram ID is {user_id}. "
            "Ask the boss to add you."
        )
        return
    if not config.PUBLIC_URL:
        await update.message.reply_text(
            "The checklist app isn't set up with a public URL yet. Ask the admin to set "
            "PUBLIC_URL in .env."
        )
        return

    tz = ZoneInfo(config.TIMEZONE)
    today_iso = datetime.now(tz).date().isoformat()
    plans = db.list_current_or_future_plan_dates(today_iso)

    # Each dated plan gets its own button, opening that specific plan by
    # id — never a generic "current checklist" link. That's what a boss
    # sending tomorrow's plan while today's is still in progress needs:
    # both stay reachable and unambiguous, instead of one link that
    # silently starts pointing at whichever is newest.
    buttons = [
        [
            InlineKeyboardButton(
                f"Work plan {datetime.fromisoformat(p['plan_date']).strftime('%d/%m/%Y')}",
                web_app=WebAppInfo(url=f"{config.PUBLIC_URL}/?plan={p['id']}"),
            )
        ]
        for p in plans
    ]

    if user_id in config.BOSS_IDS:
        buttons.append(
            [InlineKeyboardButton("Open library", web_app=WebAppInfo(url=f"{config.PUBLIC_URL}/boss"))]
        )
        buttons.append(
            [InlineKeyboardButton("Open archive", web_app=WebAppInfo(url=f"{config.PUBLIC_URL}/archive"))]
        )
        message_text = "Menu"
    elif plans:
        message_text = "Work plan" if len(plans) == 1 else "Work plans"
    else:
        message_text = "No work plan has been sent yet."

    await update.message.reply_text(message_text, reply_markup=InlineKeyboardMarkup(buttons))


async def stray_media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Photos/videos are attached from inside the checklist app, not sent here directly."""
    await update.message.reply_text("Open the checklist and tap the item to attach this.")


async def notify_crew(bot, date_str: str, plan_id: int) -> None:
    """Tell every crew member a plan is ready, with a WORK button that opens
    that specific plan."""
    if not config.CREW_IDS or not config.PUBLIC_URL:
        return
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("WORK", web_app=WebAppInfo(url=f"{config.PUBLIC_URL}/?plan={plan_id}"))]]
    )
    for crew_id in config.CREW_IDS:
        try:
            await bot.send_message(crew_id, f"Work Plan {date_str}", reply_markup=keyboard)
        except Exception:
            log.exception("Failed to notify crew id %s", crew_id)


async def notify_boss_sent(bot, date_str: str, plan_id: int) -> None:
    """Confirm to the boss(es) that the plan went out, with a button to open
    that specific plan's checklist."""
    if not config.PUBLIC_URL:
        return
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Open checklist",
                    web_app=WebAppInfo(url=f"{config.PUBLIC_URL}/?plan={plan_id}"),
                )
            ]
        ]
    )
    for boss_id in config.BOSS_IDS:
        try:
            await bot.send_message(boss_id, f"Work Plan {date_str}", reply_markup=keyboard)
        except Exception:
            log.exception("Failed to notify boss id %s", boss_id)


async def notify_all_done(bot, date_str: str) -> None:
    """Tell the boss(es) every item on the plan is finished, in plain English."""
    text = f"All tasks for {date_str} are finished."
    for boss_id in config.BOSS_IDS:
        try:
            await bot.send_message(boss_id, text)
        except Exception:
            log.exception("Failed to notify boss id %s", boss_id)


def _fmt_done_at(done_at) -> str:
    if not done_at:
        return ""
    try:
        dt = datetime.fromisoformat(done_at).astimezone(ZoneInfo(config.TIMEZONE))
    except ValueError:
        return ""
    return dt.strftime("%H:%M")


def _build_report_text(date_str: str, items: list, total: int, done: int) -> str:
    lines = [f"Daily Report — {date_str}"]
    by_villa: dict[str, list] = {}
    for item in items:
        by_villa.setdefault(item["villa"], []).append(item)

    for villa, villa_items in by_villa.items():
        by_section: dict[str, list] = {}
        for item in villa_items:
            by_section.setdefault(item["section"], []).append(item)
        for section, section_items in by_section.items():
            lines.append(f"{villa} — {section}")
            for item in section_items:
                if item["done"]:
                    time_str = _fmt_done_at(item["done_at"])
                    who = item["done_by"] or "someone"
                    lines.append(f"  ✓ {item['text']} — {who}{f' at {time_str}' if time_str else ''}")
                else:
                    lines.append(f"  ✗ {item['text']} — not done")

    lines.append("")
    lines.append(f"Total: {done}/{total} finished")
    return "\n".join(lines)


async def post_report(bot, date_str: str, items: list, total: int, done: int) -> bool:
    """Posts the daily report, then the finished items' photos/videos
    (re-sent by their stored file_id — no re-upload needed), to
    REPORTS_CHAT_ID. Returns False (and no-ops) if REPORTS_CHAT_ID isn't
    configured yet, so this never breaks the app before the channel
    exists.

    The facts always come from _build_report_text — plain, deterministic,
    assembled from the DB. Gemini only gets a chance to reword that into
    prose; if it's unavailable or fails, the plain version goes out
    instead. Either way the report always sends — AI only affects how it
    reads, never whether it goes out or what it says happened."""
    if not config.REPORTS_CHAT_ID:
        log.warning("REPORTS_CHAT_ID not set — skipping report for %s", date_str)
        return False

    plain_text = _build_report_text(date_str, items, total, done)
    prose = await gemini.write_report_prose(plain_text)
    text = prose if prose else plain_text
    try:
        await bot.send_message(config.REPORTS_CHAT_ID, text)
    except Exception:
        log.exception("Failed to post report text for %s", date_str)
        return False

    for item in items:
        if not item["done"] or not item.get("media_file_id"):
            continue
        caption = f"{item['villa']} — {item['section']}: {item['text']}"
        try:
            if item["media_type"] == "video":
                await bot.send_video(config.REPORTS_CHAT_ID, item["media_file_id"], caption=caption)
            else:
                await bot.send_photo(config.REPORTS_CHAT_ID, item["media_file_id"], caption=caption)
        except Exception:
            log.exception("Failed to forward report media for item %s", item.get("id"))

    return True
