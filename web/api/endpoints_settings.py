import asyncio
import logging

from aiogram.exceptions import TelegramRetryAfter
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import BotSettings, User, get_session


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings", tags=["Settings"])


class SettingsUpdateRequest(BaseModel):
    mandatory_channel_ids: list[str] | None = None
    post_channel_ids: list[str] | None = None
    admin_contact_link: str | None = Field(default=None, max_length=255)
    require_approval: bool | None = None
    auto_post_to_channel: bool | None = None


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
    }


@router.post("/")
async def update_bot_settings(
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
    await session.commit()
    return {"status": "success", "message": "Sozlamalar saqlandi"}


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
