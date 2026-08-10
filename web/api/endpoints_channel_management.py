import logging
from pathlib import Path

from aiogram.enums import ChatMemberStatus, ChatType
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import MAX_UPLOAD_MB
from database import BotSettings, get_session
from services.channel_post_service import post_custom_message_to_channels, unpin_message_from_channels
from services.telegram_storage_service import ALLOWED_IMAGE_TYPES, StorageError, content_matches_type


router = APIRouter(prefix="/api/admin/channel", tags=["Admin channels"])
logger = logging.getLogger(__name__)


class ChannelUpdatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channels: list[int | str] = Field(default_factory=list, max_length=20)
    auto_post: bool = True


async def _settings(session: AsyncSession) -> BotSettings:
    settings = await session.scalar(select(BotSettings).where(BotSettings.id == 1))
    if settings:
        return settings
    settings = BotSettings(id=1, mandatory_channel_ids=[], post_channel_ids=[])
    session.add(settings)
    await session.flush()
    return settings


def _chat_reference(value: int | str) -> int | str:
    raw = str(value).strip()
    if not raw:
        raise HTTPException(status_code=422, detail="Kanal ID bo'sh bo'lishi mumkin emas")
    try:
        return int(raw)
    except ValueError:
        username = raw if raw.startswith("@") else f"@{raw}"
        if len(username) < 6:
            raise HTTPException(status_code=422, detail=f"Kanal ID noto'g'ri: {raw}")
        return username


async def _validate_channel(bot, value: int | str) -> dict:
    reference = _chat_reference(value)
    try:
        chat = await bot.get_chat(reference)
        member = await bot.get_chat_member(chat.id, bot.id)
    except Exception as exc:
        logger.warning("Channel validation failed for %s: %s", value, exc)
        raise HTTPException(
            status_code=422,
            detail=f"{value}: kanal topilmadi yoki bot kanalga qo'shilmagan",
        ) from exc

    if chat.type != ChatType.CHANNEL:
        raise HTTPException(status_code=422, detail=f"{value}: bu Telegram kanal emas")
    if member.status not in {ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR}:
        raise HTTPException(status_code=422, detail=f"{value}: bot kanalda admin emas")
    if member.status == ChatMemberStatus.ADMINISTRATOR and getattr(member, "can_post_messages", False) is not True:
        raise HTTPException(status_code=422, detail=f"{value}: botga xabar joylash huquqini bering")

    return {"id": int(chat.id), "title": chat.title or str(chat.id)}


async def _save_channels(
    request: Request,
    channel_values: list[int | str],
    auto_post: bool,
    session: AsyncSession,
) -> dict:
    bot = getattr(request.app.state, "bot", None)
    if not bot:
        raise HTTPException(status_code=503, detail="Telegram bot hali ishga tushmagan")

    unique_values = []
    seen = set()
    for value in channel_values:
        normalized = str(value).strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique_values.append(value)
    if len(unique_values) > 20:
        raise HTTPException(status_code=422, detail="Ko'pi bilan 20 ta kanal sozlash mumkin")

    verified = []
    for value in unique_values:
        verified.append(await _validate_channel(bot, value))

    settings = await _settings(session)
    settings.post_channel_ids = [item["id"] for item in verified]
    settings.auto_post_to_channel = auto_post
    if verified and not settings.media_channel_id:
        settings.media_channel_id = verified[0]["id"]
        settings.media_channel_title = verified[0]["title"][:255]
    await session.commit()

    return {
        "status": "success",
        "message": f"{len(verified)} ta kanal tekshirildi va saqlandi",
        "channels": verified,
        "auto_post": settings.auto_post_to_channel,
        "media_channel_id": str(settings.media_channel_id) if settings.media_channel_id else "",
        "media_channel_title": settings.media_channel_title or "",
    }


@router.get("/channels")
async def get_configured_channels(session: AsyncSession = Depends(get_session)):
    settings = await _settings(session)
    return {
        "status": "success",
        "channels": settings.post_channel_ids or [],
        "auto_post": settings.auto_post_to_channel,
        "media_channel_id": str(settings.media_channel_id) if settings.media_channel_id else "",
        "media_channel_title": settings.media_channel_title or "",
        "media_ready": bool(settings.media_channel_id),
    }


@router.post("/configure")
async def configure_channels(
    request: Request,
    payload: ChannelUpdatePayload,
    session: AsyncSession = Depends(get_session),
):
    return await _save_channels(request, payload.channels, payload.auto_post, session)


@router.post("/update-channels")
async def update_channels_compat(
    request: Request,
    channels: str = Form(""),
    auto_post: bool = Form(True),
    session: AsyncSession = Depends(get_session),
):
    values = [part.strip() for part in channels.split(",") if part.strip()]
    return await _save_channels(request, values, auto_post, session)


@router.post("/post-custom")
async def post_custom_to_channels(
    request: Request,
    text: str = Form(..., min_length=1, max_length=4096),
    pin_message: bool = Form(False),
    photo: UploadFile | None = File(None),
    session: AsyncSession = Depends(get_session),
):
    bot = getattr(request.app.state, "bot", None)
    if not bot:
        raise HTTPException(status_code=503, detail="Telegram bot hali ishga tushmagan")

    message_text = text.strip()
    if not message_text:
        raise HTTPException(status_code=422, detail="Xabar matnini kiriting")

    photo_bytes = None
    photo_name = None
    photo_mime_type = None
    if photo and photo.filename:
        mime_type = (photo.content_type or "").split(";", 1)[0].lower()
        if mime_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(status_code=415, detail="Faqat JPG, PNG, WEBP yoki GIF rasm yuborish mumkin")
        max_bytes = MAX_UPLOAD_MB * 1024 * 1024
        photo_bytes = await photo.read(max_bytes + 1)
        await photo.close()
        if len(photo_bytes) > max_bytes:
            raise HTTPException(status_code=413, detail=f"Rasm hajmi {MAX_UPLOAD_MB} MB dan oshmasligi kerak")
        if not content_matches_type(photo_bytes, mime_type):
            raise HTTPException(status_code=415, detail="Rasm faylining tarkibi noto'g'ri")
        photo_name = Path(photo.filename).name
        photo_mime_type = mime_type

    try:
        posted = await post_custom_message_to_channels(
            bot=bot,
            session=session,
            text=message_text,
            photo_bytes=photo_bytes,
            photo_filename=photo_name,
            photo_mime_type=photo_mime_type,
            pin_message=pin_message,
        )
    except StorageError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not posted:
        raise HTTPException(
            status_code=422,
            detail="Xabar yuborilmadi. Kanal sozlamasi va bot admin huquqlarini tekshiring",
        )
    return {
        "status": "success",
        "message": f"Xabar {len(posted)} ta kanalga yuborildi" + (" va mahkamlandi" if pin_message else ""),
        "posted": posted,
    }


@router.post("/unpin-all")
async def unpin_all_messages(request: Request, session: AsyncSession = Depends(get_session)):
    bot = getattr(request.app.state, "bot", None)
    if not bot:
        raise HTTPException(status_code=503, detail="Telegram bot hali ishga tushmagan")
    completed = await unpin_message_from_channels(bot, session)
    if not completed:
        raise HTTPException(status_code=422, detail="Pinlar olinmadi. Kanal va bot huquqlarini tekshiring")
    return {"status": "success", "message": f"{len(completed)} ta kanaldagi pinlar olib tashlandi"}


@router.post("/test-channel/{channel_id}")
async def test_channel(channel_id: str, request: Request):
    bot = getattr(request.app.state, "bot", None)
    if not bot:
        raise HTTPException(status_code=503, detail="Telegram bot hali ishga tushmagan")
    channel = await _validate_channel(bot, channel_id)
    try:
        message = await bot.send_message(
            chat_id=channel["id"],
            text="Kanal muvaffaqiyatli ulandi.",
            disable_notification=True,
        )
        await bot.delete_message(chat_id=channel["id"], message_id=message.message_id)
    except Exception as exc:
        logger.warning("Channel send/delete test failed for %s: %s", channel_id, exc)
        raise HTTPException(
            status_code=422,
            detail="Botga xabar joylash va xabarni o'chirish huquqlarini bering",
        ) from exc
    return {
        "status": "success",
        "message": f"{channel['title']} kanali to'liq ishlayapti",
        "channel": channel,
    }
