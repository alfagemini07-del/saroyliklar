import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()

_BASE_DIR = Path(__file__).resolve().parent


def _env_text(name: str, default: str = "") -> str:
    """Read a text env value and tolerate KEY=value pasted into Render's Value field."""
    value = os.getenv(name, default).strip()
    prefix = f"{name}="
    if value.startswith(prefix):
        value = value[len(prefix):].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    return value


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int_list(name: str) -> list[int]:
    values: list[int] = []
    for item in os.getenv(name, "").split(","):
        item = item.strip()
        if item:
            try:
                values.append(int(item))
            except ValueError:
                continue
    return values


# Application / Render
APP_NAME = _env_text("APP_NAME", "Saroyliklar")
ENVIRONMENT = _env_text("ENVIRONMENT", "development").lower()
DEBUG = _env_bool("DEBUG", ENVIRONMENT != "production")
PORT = _env_int("PORT", 8000)
RENDER_EXTERNAL_URL = _env_text("RENDER_EXTERNAL_URL").rstrip("/")
PUBLIC_BASE_URL = (
    RENDER_EXTERNAL_URL
    or _env_text("PUBLIC_BASE_URL").rstrip("/")
    or _env_text("WEBHOOK_URL").rstrip("/")
    or "http://localhost:8000"
)
WEBHOOK_URL = PUBLIC_BASE_URL  # Backward-compatible name used by a few handlers.
WEBHOOK_PATH = _env_text("WEBHOOK_PATH", "/telegram/webhook")
WEBHOOK_SECRET = _env_text("WEBHOOK_SECRET")
WEBAPP_URL = (
    f"{PUBLIC_BASE_URL}/webapp"
    if RENDER_EXTERNAL_URL
    else _env_text("WEBAPP_URL", f"{PUBLIC_BASE_URL}/webapp").rstrip("/")
)
BACKEND_URL = PUBLIC_BASE_URL

# Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = _env_int_list("ADMIN_IDS")

# Supabase Postgres. Use the Session pooler URL on port 5432 on Render.
DATABASE_URL = _env_text(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/saroyliklar",
)
DB_POOL_SIZE = _env_int("DB_POOL_SIZE", 5)
DB_MAX_OVERFLOW = _env_int("DB_MAX_OVERFLOW", 5)
DB_SSL = _env_bool("DB_SSL", "supabase.co" in DATABASE_URL)

# Admin panel
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
ADMIN_SECRET_KEY = os.getenv("ADMIN_SECRET_KEY", "")
ADMIN_COOKIE_NAME = "saroyliklar_admin"

# Media is archived in a private Telegram channel selected from the admin panel.
MAX_UPLOAD_MB = _env_int("MAX_UPLOAD_MB", 10)
MEDIA_CACHE_MB = _env_int("MEDIA_CACHE_MB", 64)

# Local-only WebApp testing. Never enable this on Render.
DEV_TELEGRAM_ID = _env_int("DEV_TELEGRAM_ID", 0)

# Optional AI categorization
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash"]

CATEGORIES = {
    "grocery": {"icon": "🛒", "name": "Oziq-ovqat", "color": "#16865b"},
    "food": {"icon": "🍽️", "name": "Taomlar", "color": "#e76f2e"},
    "clothing": {"icon": "👕", "name": "Kiyim-kechak", "color": "#2563a8"},
    "home": {"icon": "🛋️", "name": "Uy-ro'zg'or", "color": "#8b5a2b"},
    "beauty": {"icon": "✨", "name": "Go'zallik", "color": "#c44569"},
    "health": {"icon": "💊", "name": "Salomatlik", "color": "#0f8b8d"},
    "electronics": {"icon": "📱", "name": "Elektronika", "color": "#5b5bd6"},
    "construction": {"icon": "🧰", "name": "Qurilish", "color": "#b7791f"},
    "services": {"icon": "🧑‍🔧", "name": "Xizmatlar", "color": "#277da1"},
    "other": {"icon": "📦", "name": "Boshqa", "color": "#59636e"},
}

CATEGORY_NAMES_FOR_AI = {
    key: value["name"] for key, value in CATEGORIES.items()
}

CURRENCIES = ["UZS", "USD"]
MAX_AD_IMAGES = 5
MAX_PLACE_PHOTOS = 50
AD_EXPIRE_DAYS = 30
FREE_ADS_PER_USER = 3

REGIONS = [
    "Toshkent shahri", "Toshkent viloyati", "Samarqand", "Buxoro",
    "Andijon", "Farg'ona", "Namangan", "Qashqadaryo", "Surxondaryo",
    "Xorazm", "Navoiy", "Sirdaryo", "Jizzax", "Qoraqalpog'iston",
]


def validate_runtime_config() -> list[str]:
    """Return configuration errors that make a production start unsafe."""
    errors: list[str] = []
    required = {
        "BOT_TOKEN": BOT_TOKEN,
        "DATABASE_URL": DATABASE_URL,
        "PUBLIC_BASE_URL": PUBLIC_BASE_URL,
        "WEBHOOK_SECRET": WEBHOOK_SECRET,
        "ADMIN_PASSWORD": ADMIN_PASSWORD,
        "ADMIN_SECRET_KEY": ADMIN_SECRET_KEY,
    }
    for name, value in required.items():
        if not value:
            errors.append(f"{name} is not configured")
    if ENVIRONMENT == "production" and not PUBLIC_BASE_URL.startswith("https://"):
        errors.append("PUBLIC_BASE_URL must use HTTPS in production")
    if ENVIRONMENT == "production" and not WEBAPP_URL.startswith("https://"):
        errors.append("WEBAPP_URL must be a valid HTTPS URL")
    if ENVIRONMENT == "production" and DEV_TELEGRAM_ID:
        errors.append("DEV_TELEGRAM_ID must be disabled in production")
    if MAX_UPLOAD_MB < 1 or MAX_UPLOAD_MB > 10:
        errors.append("MAX_UPLOAD_MB must be between 1 and 10 for Telegram media storage")
    if MEDIA_CACHE_MB < 0 or MEDIA_CACHE_MB > 256:
        errors.append("MEDIA_CACHE_MB must be between 0 and 256")
    return errors
