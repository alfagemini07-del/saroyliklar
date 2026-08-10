import asyncio
import logging

from aiogram.exceptions import TelegramRetryAfter
from aiogram.enums import ChatMemberStatus, ChatType
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import BotSettings, User, get_session
from services.telegram_storage_service import StorageError, get_storage


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings", tags=["Settings"])


class SettingsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mandatory_channel_ids: list[str] | None = None
    post_channel_ids: list[str] | None = None
    admin_contact_link: str | None = Field(default=None, max_length=255)
    require_approval: bool | None = None
    auto_post_to_channel: bool | None = None
    media_channel_id: int | str | None = None


class BroadcastRequest(BaseModel):
    message_text: str = Field(min_length=1, max_length=4096)


async def _settings(session: AsyncSession) -> BotSettings:
    settings = await session.scalar(select(BotSettings).where(BotSettings.id == 1))
    if settings:
        return settings
    settings = BotSettings(id=1, mandatory_channel_ids=[], post_channel_ids=[])
    session.add(settings)
    await session.commit()
    await session.refresh(settings)
    return settings


@router.get("/")
async def get_bot_settings(session: AsyncSession = Depends(get_session)):
    settings = await _settings(session)
    return {
        "id": settings.id,
        "mandatory_channel_ids": settings.mandatory_channel_ids or [],
        "post_channel_ids": settings.post_channel_ids or [],
        "admin_contact_link": settings.admin_contact_link or "",
        "require_approval": settings.require_approval,
        "auto_post_to_channel": settings.auto_post_to_channel,
        "media_channel_id": str(settings.media_channel_id) if settings.media_channel_id else "",
        "media_channel_title": settings.media_channel_title or "",
        "media_storage_ready": bool(settings.media_channel_id),
    }


@router.post("/")
async def update_bot_settings(
    request: Request,
    payload: SettingsUpdateRequest,
    session: AsyncSession = Depends(get_session),
):
    settings = await _settings(session)
    if payload.mandatory_channel_ids is not None:
        settings.mandatory_channel_ids = payload.mandatory_channel_ids
    if payload.post_channel_ids is not None:
        settings.post_channel_ids = payload.post_channel_ids
    if payload.admin_contact_link is not None:
        settings.admin_contact_link = payload.admin_contact_link.strip() or None
    if payload.require_approval is not None:
        settings.require_approval = payload.require_approval
    if payload.auto_post_to_channel is not None:
        settings.auto_post_to_channel = payload.auto_post_to_channel
    if payload.media_channel_id is not None:
        raw_channel = str(payload.media_channel_id).strip()
        if not raw_channel:
            settings.media_channel_id = None
            settings.media_channel_title = None
        else:
            chat_ref: int | str
            try:
                chat_ref = int(raw_channel)
            except ValueError:
                chat_ref = raw_channel if raw_channel.startswith("@") else f"@{raw_channel}"
            bot = getattr(request.app.state, "bot", None)
            if not bot:
                raise HTTPException(status_code=500, detail="Bot obyekti topilmadi")
            try:
                chat = await bot.get_chat(chat_ref)
                member = await bot.get_chat_member(chat.id, bot.id)
            except Exception as exc:
                raise HTTPException(
                    status_code=422,
                    detail="Kanal topilmadi. Kanal ID va bot adminligini tekshiring",
                ) from exc
            if chat.type != ChatType.CHANNEL:
                raise HTTPException(status_code=422, detail="Media bazasi uchun Telegram kanal tanlang")
            if member.status not in {ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR}:
                raise HTTPException(status_code=422, detail="Bot tanlangan kanalda admin emas")
            if member.status == ChatMemberStatus.ADMINISTRATOR and getattr(member, "can_post_messages", False) is not True:
                raise HTTPException(status_code=422, detail="Botga kanalda xabar joylash huquqini bering")
            if member.status == ChatMemberStatus.ADMINISTRATOR and getattr(member, "can_delete_messages", False) is not True:
                raise HTTPException(status_code=422, detail="Botga kanaldagi xabarlarni o'chirish huquqini bering")
            settings.media_channel_id = int(chat.id)
            settings.media_channel_title = (chat.title or str(chat.id))[:255]
    await session.commit()
    await session.refresh(settings)
    logger.info(
        "Bot settings saved: media_channel_id=%s media_channel_title=%s",
        settings.media_channel_id,
        settings.media_channel_title,
    )
    return {
        "status": "success",
        "message": "Sozlamalar saqlandi",
        "media_channel_id": str(settings.media_channel_id) if settings.media_channel_id else "",
        "media_channel_title": settings.media_channel_title or "",
        "media_storage_ready": bool(settings.media_channel_id),
    }


@router.get("/media-status")
async def media_storage_status():
    try:
        channel_id = await get_storage().resolve_channel_id()
    except StorageError as exc:
        return {"ready": False, "channel_id": "", "detail": str(exc)}
    return {"ready": True, "channel_id": str(channel_id), "detail": "Media kanali ishlashga tayyor"}


async def _broadcast(bot, user_ids: list[int], message_text: str) -> None:
    sent = 0
    failed = 0
    for user_id in user_ids:
        try:
            await bot.send_message(chat_id=user_id, text=message_text, parse_mode="HTML")
            sent += 1
            await asyncio.sleep(0.05)
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after)
            try:
                await bot.send_message(chat_id=user_id, text=message_text, parse_mode="HTML")
                sent += 1
            except Exception:
                failed += 1
        except Exception:
            failed += 1
    logger.info("Broadcast finished: sent=%s failed=%s", sent, failed)


@router.post("/broadcast")
async def send_web_broadcast(
    request: Request,
    payload: BroadcastRequest,
    session: AsyncSession = Depends(get_session),
):
    bot = getattr(request.app.state, "bot", None)
    if not bot:
        raise HTTPException(status_code=500, detail="Bot obyekti topilmadi")
    message = payload.message_text.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Xabarni kiriting")
    user_ids = list((await session.execute(select(User.telegram_id))).scalars())
    asyncio.create_task(_broadcast(bot, user_ids, message))
    return {
        "status": "success",
        "message": f"Xabar {len(user_ids)} ta foydalanuvchiga yuborish navbatiga qo'shildi",
    }
