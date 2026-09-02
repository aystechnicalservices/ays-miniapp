import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
BOSS_ID = int(os.environ.get("BOSS_ID", "0") or "0")  # primary boss — has library access
STORAGE_CHAT_ID = int(os.environ.get("STORAGE_CHAT_ID", "0") or "0")  # media relays here
EXTRA_BOSS_IDS = {
    int(x) for x in os.environ.get("EXTRA_BOSS_IDS", "").split(",") if x.strip()
}
BOSS_IDS = {BOSS_ID} | EXTRA_BOSS_IDS  # everyone allowed into the boss library view
CREW_IDS = {
    int(x) for x in os.environ.get("CREW_IDS", "").split(",") if x.strip()
}  # who gets the "Work Plan ..." notification when a plan is sent
ALLOWED_IDS = BOSS_IDS | CREW_IDS  # only these Telegram IDs may use the bot/Mini App
TIMEZONE = os.environ.get("TIMEZONE", "Asia/Dubai")
PUBLIC_URL = os.environ.get("PUBLIC_URL", "").rstrip("/")
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "ays.db"
MEDIA_CACHE_DIR = PROJECT_ROOT / "media_cache"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set. Copy .env.example to .env and fill it in.")
if not BOSS_ID:
    raise RuntimeError("BOSS_ID is not set. Copy .env.example to .env and fill it in.")
if not STORAGE_CHAT_ID:
    raise RuntimeError("STORAGE_CHAT_ID is not set. Copy .env.example to .env and fill it in.")
