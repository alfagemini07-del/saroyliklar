import hashlib
import hmac
import io
import logging
import mimetypes
import os
import re
from dataclasses import dataclass
from pathlib import Path

from aiogram import Bot
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.types import BufferedInputFile
from sqlalchemy import select

from config import ADMIN_SECRET_KEY, BOT_TOKEN, MAX_UPLOAD_MB, PUBLIC_BASE_URL
from database import AsyncSessionLocal, BotSettings, MediaObject


logger = logging.getLogger(__name__)
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/webm", "video/quicktime"}
ALLOWED_MEDIA_TYPES = ALLOWED_IMAGE_TYPES | ALLOWED_VIDEO_TYPES
_MEDIA_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.I)


@dataclass(slots=True)
class StoredMedia:
    file_id: str
    public_url: str
    mime_type: str
    media_type: str
    size_bytes: int
    name: str
    telegram_file_id: str | None = None


class StorageError(RuntimeError):
    pass


def _signature(media_id: str) -> str:
    secret = (ADMIN_SECRET_KEY or BOT_TOKEN).encode()
    return hmac.new(secret, media_id.encode(), hashlib.sha256).hexdigest()[:32]


def valid_media_signature(media_id: str, signature: str) -> bool:
    return bool(signature) and hmac.compare_digest(_signature(media_id), signature)


def storage_public_url(file_id: str, mime_type: str = "image/jpeg") -> str:
    del mime_type
    if not file_id:
        return ""
    if file_id.startswith(("http://", "https://", "/")):
        return file_id
    if not _MEDIA_ID_RE.fullmatch(file_id):
        return ""
    return f"{PUBLIC_BASE_URL.rstrip('/')}/media/{file_id}?sig={_signature(file_id)}"


def media_public_url(media) -> str | None:
    if not media:
        return None
    file_id = getattr(media, "file_id", None)
    generated = storage_public_url(file_id) if file_id else ""
    return generated or getattr(media, "public_url", None) or None


def _safe_filename(filename: str, mime_type: str) -> str:
    original = Path(filename or "media").name
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", Path(original).stem).strip("-")[:80] or "media"
    extension = mimetypes.guess_extension(mime_type) or Path(original).suffix or ".bin"
    if extension == ".jpe":
        extension = ".jpg"
    return f"{stem}{extension.lower()}"


def _content_matches_type(content: bytes, mime_type: str) -> bool:
    if mime_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if mime_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if mime_type == "image/webp":
        return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    if mime_type == "image/gif":
        return content.startswith((b"GIF87a", b"GIF89a"))
    if mime_type == "video/webm":
        return content.startswith(b"\x1aE\xdf\xa3")
    if mime_type in {"video/mp4", "video/quicktime"}:
        return len(content) >= 12 and content[4:8] == b"ftyp"
    return False


class TelegramChannelStorage:
    def __init__(self) -> None:
        self.bot: Bot | None = None

    def configure(self, bot: Bot) -> None:
        self.bot = bot

    @property
    def configured(self) -> bool:
        return self.bot is not None

    def _bot(self) -> Bot:
        if not self.bot:
            raise StorageError("Telegram media storage ishga tushmagan")
        return self.bot

    async def resolve_channel_id(self) -> int:
        async with AsyncSessionLocal() as session:
            settings = await session.scalar(select(BotSettings).where(BotSettings.id == 1))
            candidates = []
            if settings and settings.media_channel_id:
                candidates.append(settings.media_channel_id)
            env_channel = os.getenv("MEDIA_CHANNEL_ID", "").strip()
            if env_channel:
                candidates.append(env_channel)
            if settings:
                candidates.extend(settings.post_channel_ids or [])
            if not candidates:
                raise StorageError("Admin panelda media saqlash kanali belgilanmagan")

            seen: set[str] = set()
            for candidate in candidates:
                raw_channel = str(candidate).strip()
                if not raw_channel or raw_channel in seen:
                    continue
                seen.add(raw_channel)
                try:
                    chat_ref: int | str = int(raw_channel)
                except ValueError:
                    chat_ref = raw_channel if raw_channel.startswith("@") else f"@{raw_channel}"
                try:
                    chat = await self._bot().get_chat(chat_ref)
                    member = await self._bot().get_chat_member(chat.id, self._bot().id)
                except Exception as exc:
                    logger.warning("Media channel candidate is unavailable %s: %s", raw_channel, exc)
                    continue
                if chat.type != ChatType.CHANNEL:
                    continue
                if member.status not in {ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR}:
                    continue
                if member.status == ChatMemberStatus.ADMINISTRATOR and getattr(member, "can_post_messages", False) is not True:
                    continue

                if settings and settings.media_channel_id != int(chat.id):
                    settings.media_channel_id = int(chat.id)
                    settings.media_channel_title = (chat.title or str(chat.id))[:255]
                    await session.commit()
                return int(chat.id)

            raise StorageError("Media kanali topilmadi yoki botda kanalga xabar joylash huquqi yo'q")

    async def upload(
        self,
        content: bytes,
        filename: str,
        mime_type: str,
        prefix: str = "media",
    ) -> StoredMedia:
        mime_type = (mime_type or "").split(";", 1)[0].strip().lower()
        if mime_type not in ALLOWED_MEDIA_TYPES:
            raise StorageError("Faqat JPG, PNG, WEBP, GIF, MP4, WEBM va MOV fayllari qabul qilinadi")
        if not content:
            raise StorageError("Yuklangan fayl bo'sh")
        if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
            raise StorageError(f"Fayl hajmi {MAX_UPLOAD_MB} MB dan oshmasligi kerak")
        if not _content_matches_type(content, mime_type):
            raise StorageError("Fayl tarkibi tanlangan media turiga mos emas")

        channel_id = await self.resolve_channel_id()
        safe_name = _safe_filename(filename, mime_type)
        media_type = "video" if mime_type.startswith("video/") else "image"
        caption = f"Saroyliklar media | {prefix[:40]} | {safe_name}"[:1024]
        try:
            message = await self._bot().send_document(
                chat_id=channel_id,
                document=BufferedInputFile(content, filename=safe_name),
                caption=caption,
                disable_notification=True,
                protect_content=True,
            )
        except Exception as exc:
            logger.exception("Telegram media channel upload failed")
            raise StorageError("Media kanaliga fayl yuborilmadi. Bot adminligini tekshiring") from exc
        if not message.document:
            try:
                await self._bot().delete_message(channel_id, message.message_id)
            except Exception:
                pass
            raise StorageError("Telegram yuklangan fayl identifikatorini qaytarmadi")

        record = MediaObject(
            channel_id=channel_id,
            message_id=message.message_id,
            telegram_file_id=message.document.file_id,
            telegram_file_unique_id=message.document.file_unique_id,
            filename=safe_name,
            mime_type=mime_type,
            media_type=media_type,
            size_bytes=len(content),
        )
        async with AsyncSessionLocal() as session:
            session.add(record)
            try:
                await session.commit()
                await session.refresh(record)
            except Exception:
                await session.rollback()
                try:
                    await self._bot().delete_message(channel_id, message.message_id)
                except Exception:
                    pass
                raise

        return StoredMedia(
            file_id=record.id,
            public_url=storage_public_url(record.id, mime_type),
            mime_type=mime_type,
            media_type=media_type,
            size_bytes=len(content),
            name=safe_name,
            telegram_file_id=message.document.file_id,
        )

    async def get_record(self, media_id: str) -> MediaObject | None:
        if not media_id or not _MEDIA_ID_RE.fullmatch(media_id):
            return None
        async with AsyncSessionLocal() as session:
            return await session.get(MediaObject, media_id)

    async def download(self, file_id: str) -> bytes:
        record = await self.get_record(file_id)
        if not record:
            raise StorageError("Media fayli topilmadi")
        output = io.BytesIO()
        try:
            await self._bot().download(record.telegram_file_id, destination=output)
        except Exception as exc:
            logger.exception("Telegram media download failed: %s", file_id)
            raise StorageError("Telegram kanalidan faylni olib bo'lmadi") from exc
        return output.getvalue()

    async def delete(self, file_id: str) -> None:
        record = await self.get_record(file_id)
        if not record:
            return
        try:
            await self._bot().delete_message(record.channel_id, record.message_id)
        except Exception as exc:
            logger.warning("Telegram archive message could not be deleted %s: %s", record.message_id, exc)
        async with AsyncSessionLocal() as session:
            attached = await session.get(MediaObject, file_id)
            if attached:
                await session.delete(attached)
                await session.commit()


_storage = TelegramChannelStorage()


def configure_storage(bot: Bot) -> None:
    _storage.configure(bot)


def get_storage() -> TelegramChannelStorage:
    return _storage
