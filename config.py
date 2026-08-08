import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()

_BASE_DIR = Path(__file__).resolve().parent


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
APP_NAME = os.getenv("APP_NAME", "Saroyliklar")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
DEBUG = _env_bool("DEBUG", ENVIRONMENT != "production")
PORT = _env_int("PORT", 8000)
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", os.getenv("WEBHOOK_URL", "http://localhost:8000")).rstrip("/")
WEBHOOK_URL = PUBLIC_BASE_URL  # Backward-compatible name used by a few handlers.
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/telegram/webhook")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
WEBAPP_URL = os.getenv("WEBAPP_URL", f"{PUBLIC_BASE_URL}/webapp")
BACKEND_URL = PUBLIC_BASE_URL

# Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = _env_int_list("ADMIN_IDS")

# Supabase Postgres. Use the Session pooler URL on port 5432 on Render.
DATABASE_URL = os.getenv(
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

# Google Drive OAuth. A personal Drive account must use an OAuth refresh token.
GOOGLE_DRIVE_CLIENT_ID = os.getenv("GOOGLE_DRIVE_CLIENT_ID", "")
GOOGLE_DRIVE_CLIENT_SECRET = os.getenv("GOOGLE_DRIVE_CLIENT_SECRET", "")
GOOGLE_DRIVE_REFRESH_TOKEN = os.getenv("GOOGLE_DRIVE_REFRESH_TOKEN", "")
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
GOOGLE_DRIVE_PUBLIC = _env_bool("GOOGLE_DRIVE_PUBLIC", True)
MAX_UPLOAD_MB = _env_int("MAX_UPLOAD_MB", 20)

# Local-only WebApp testing. Never enable this on Render.
DEV_TELEGRAM_ID = _env_int("DEV_TELEGRAM_ID", 0)

# Optional AI categorization
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash"]

CATEGORIES = {
    "housing": {"icon": "🏠", "name": "Uy-joy", "color": "#e4572e"},
    "food": {"icon": "🍽️", "name": "Ovqatlanish", "color": "#f3a712"},
    "grocery": {"icon": "🛒", "name": "Oziq-ovqat", "color": "#2a9d63"},
    "hardware": {"icon": "🔧", "name": "Qurilish va jihoz", "color": "#6c5ce7"},
    "services": {"icon": "💼", "name": "Xizmatlar", "color": "#277da1"},
    "entertainment": {"icon": "🎯", "name": "Ko'ngilochar", "color": "#ef476f"},
    "other": {"icon": "📦", "name": "Boshqa", "color": "#59636e"},
}

CATEGORY_NAMES_FOR_AI = {
    key: value["name"] for key, value in CATEGORIES.items()
}

CURRENCIES = ["UZS", "USD"]
MAX_AD_IMAGES = 5
MAX_PLACE_PHOTOS = 20
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
        "GOOGLE_DRIVE_CLIENT_ID": GOOGLE_DRIVE_CLIENT_ID,
        "GOOGLE_DRIVE_CLIENT_SECRET": GOOGLE_DRIVE_CLIENT_SECRET,
        "GOOGLE_DRIVE_REFRESH_TOKEN": GOOGLE_DRIVE_REFRESH_TOKEN,
        "GOOGLE_DRIVE_FOLDER_ID": GOOGLE_DRIVE_FOLDER_ID,
    }
    for name, value in required.items():
        if not value:
            errors.append(f"{name} is not configured")
    if ENVIRONMENT == "production" and not PUBLIC_BASE_URL.startswith("https://"):
        errors.append("PUBLIC_BASE_URL must use HTTPS in production")
    if ENVIRONMENT == "production" and DEV_TELEGRAM_ID:
        errors.append("DEV_TELEGRAM_ID must be disabled in production")
    return errors
