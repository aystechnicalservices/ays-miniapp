import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from . import config, db

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
    if config.MAINTENANCE_MODE and user_id not in config.BOSS_IDS:
        await update.message.reply_text(
            "The work plan is being updated. Please check back in a few minutes."
        )
        return
    if not config.PUBLIC_URL:
        await update.message.reply_text(
            "The checklist app isn't set up with a public URL yet. Ask the admin to set "
            "PUBLIC_URL in .env."
        )
        return
    # ?checklist=1 stops the page bouncing bosses over to the library, which
    # is what the blue menu button relies on.
    checklist_url = f"{config.PUBLIC_URL}/?checklist=1"
    buttons = [[InlineKeyboardButton("Open checklist", web_app=WebAppInfo(url=checklist_url))]]
    if user_id in config.BOSS_IDS:
        buttons.append(
            [InlineKeyboardButton("Open library", web_app=WebAppInfo(url=f"{config.PUBLIC_URL}/boss"))]
        )
        buttons.append(
            [InlineKeyboardButton("Open archive", web_app=WebAppInfo(url=f"{config.PUBLIC_URL}/archive"))]
        )
        message_text = "Menu"
    else:
        tz = ZoneInfo(config.TIMEZONE)
        sent_at = db.get_plan_sent_at()
        if sent_at:
            date_str = datetime.fromisoformat(sent_at).astimezone(tz).strftime("%d/%m/%Y")
        else:
            date_str = datetime.now(tz).strftime("%d/%m/%Y")
        message_text = f"Work plan {date_str}"
    await update.message.reply_text(message_text, reply_markup=InlineKeyboardMarkup(buttons))


async def stray_media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Photos/videos are attached from inside the checklist app, not sent here directly."""
    await update.message.reply_text("Open the checklist and tap the item to attach this.")


async def notify_crew(bot, date_str: str) -> None:
    """Tell every crew member a plan is ready, with a WORK button that opens it."""
    if not config.CREW_IDS or not config.PUBLIC_URL:
        return
    if config.MAINTENANCE_MODE:
        # Mid-maintenance sends are the boss testing; don't buzz the crew's
        # phones with a plan they can't open yet.
        log.info("Maintenance mode on — skipping crew notification")
        return
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("WORK", web_app=WebAppInfo(url=config.PUBLIC_URL))]]
    )
    for crew_id in config.CREW_IDS:
        try:
            await bot.send_message(crew_id, f"Work Plan {date_str}", reply_markup=keyboard)
        except Exception:
            log.exception("Failed to notify crew id %s", crew_id)


async def notify_boss_sent(bot, date_str: str) -> None:
    """Confirm to the boss(es) that the plan went out, with a button to open it."""
    if not config.PUBLIC_URL:
        return
    # This button goes to bosses, who would otherwise be redirected to the
    # library — ?checklist=1 keeps it showing the checklist it advertises.
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Open checklist",
                    web_app=WebAppInfo(url=f"{config.PUBLIC_URL}/?checklist=1"),
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
