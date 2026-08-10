import logging
from contextlib import asynccontextmanager

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import MenuButtonWebApp, WebAppInfo
from fastapi import FastAPI

from config import (
    BOT_TOKEN,
    ENVIRONMENT,
    PORT,
    PUBLIC_BASE_URL,
    WEBHOOK_PATH,
    WEBHOOK_SECRET,
    WEBAPP_URL,
    validate_runtime_config,
)
from database import close_db, init_db
from handlers.admin import router as admin_router
from handlers.place import router as place_router
from handlers.start import router as start_router
from middlewares.db import DbMiddleware
from middlewares.throttling import ThrottlingMiddleware
from services.telegram_storage_service import configure_storage
from web.main_web import init_web


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not configured")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
dp.update.middleware(DbMiddleware())
dp.message.middleware(ThrottlingMiddleware(limit=0.8))
dp.callback_query.middleware(ThrottlingMiddleware(limit=0.35))
dp.include_router(start_router)
dp.include_router(place_router)
dp.include_router(admin_router)


@asynccontextmanager
async def lifespan(_: FastAPI):
    config_errors = validate_runtime_config()
    if config_errors and ENVIRONMENT == "production":
        raise RuntimeError("Invalid production configuration: " + "; ".join(config_errors))
    for error in config_errors:
        logger.warning("Configuration: %s", error)

    await init_db()
    configure_storage(bot)
    separator = "&" if "?" in WEBAPP_URL else "?"
    try:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Saroylik bozori",
                web_app=WebAppInfo(url=f"{WEBAPP_URL}{separator}v=9"),
            )
        )
    except Exception as exc:
        logger.warning("Telegram Mini App menu button could not be updated: %s", exc)
    webhook_url = f"{PUBLIC_BASE_URL}{WEBHOOK_PATH}"
    await bot.set_webhook(
        url=webhook_url,
        secret_token=WEBHOOK_SECRET or None,
        allowed_updates=dp.resolve_used_update_types(),
        drop_pending_updates=False,
    )
    logger.info("Telegram webhook is active: %s", webhook_url)
    try:
        yield
    finally:
        # Keep the webhook registered during Render deploys and cold restarts.
        await bot.session.close()
        await close_db()


app = init_web(bot, dp)
app.router.lifespan_context = lifespan


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
