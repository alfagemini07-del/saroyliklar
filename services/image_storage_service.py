"""Compatibility helpers for media received by the Telegram bot."""

import io
import logging
from pathlib import Path

from aiogram import Bot

from services.supabase_storage_service import get_storage, storage_public_url


logger = logging.getLogger(__name__)


async def upload_telegram_media(bot: Bot, file_id: str, prefix: str = "telegram"):
    file_info = await bot.get_file(file_id)
    output = io.BytesIO()
    await bot.download_file(file_info.file_path, destination=output)
    content = output.getvalue()
    extension = Path(file_info.file_path or "media.jpg").suffix or ".jpg"
    mime_type = "video/mp4" if extension.lower() in {".mp4", ".mov", ".webm"} else "image/jpeg"
    return await get_storage().upload(content, f"telegram{extension}", mime_type, prefix=prefix)


async def download_and_save_telegram_photo(bot: Bot, file_id: str) -> str | None:
    if not file_id:
        return None
    if file_id.startswith(("http://", "https://")):
        return file_id
    try:
        stored = await upload_telegram_media(bot, file_id, prefix="telegram-photo")
        return stored.public_url
    except Exception as exc:
        logger.exception("Telegram media upload to Drive failed: %s", exc)
        return None


def get_image_url_sync(file_id: str) -> str | None:
    if not file_id:
        return None
    if file_id.startswith(("http://", "https://", "/")):
        return file_id
    return storage_public_url(file_id)
