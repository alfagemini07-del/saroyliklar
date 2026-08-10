"""
Kanal management API - admin tomonidan maxsus postlar va pin management
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Form, UploadFile, File, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_session, BotSettings
from aiogram.types import BufferedInputFile
from services.channel_post_service import post_custom_message_to_channels, unpin_message_from_channels

router = APIRouter(prefix="/api/admin/channel")
logger = logging.getLogger(__name__)

@router.get("/channels")
async def get_configured_channels(session: AsyncSession = Depends(get_session)):
    """Sozlangan kanallar ro'yxati"""
    result = await session.execute(select(BotSettings).where(BotSettings.id == 1))
    settings = result.scalar_one_or_none()

    if not settings:
        return {"status": "success", "channels": [], "auto_post": True}

    return {
        "status": "success",
        "channels": settings.post_channel_ids or [],
        "auto_post": settings.auto_post_to_channel if settings else True
    }


@router.post("/update-channels")
async def update_channels(
    channels: str = Form(...),  # Vergul bilan ajratilgan ID'lar
    auto_post: bool = Form(True),
    session: AsyncSession = Depends(get_session)
):
    """Kanallar ro'yxatini yangilash"""
    try:
        # Channels ni parse qilish
        channel_list = []
        if channels and channels.strip():
            parts = channels.replace(" ", "").split(",")
            for part in parts:
                if part and (part.startswith("-") or part.isdigit()):
                    try:
                        channel_list.append(int(part))
                    except ValueError:
                        continue

        # Settings ni yangilash
        result = await session.execute(select(BotSettings).where(BotSettings.id == 1))
        settings = result.scalar_one_or_none()

        if not settings:
            settings = BotSettings(id=1)
            session.add(settings)

        settings.post_channel_ids = channel_list
        settings.auto_post_to_channel = auto_post
        if channel_list and not settings.media_channel_id:
            settings.media_channel_id = int(channel_list[0])
            settings.media_channel_title = f"Kanal {channel_list[0]}"

        await session.commit()

        return {
            "status": "success",
            "message": f"{len(channel_list)} ta kanal saqlandi",
            "channels": channel_list,
            "media_channel_id": str(settings.media_channel_id) if settings.media_channel_id else "",
        }

    except Exception as e:
        logger.error(f"Kanallarni yangilashda xato: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/post-custom")
async def post_custom_to_channels(
    request: Request,
    text: str = Form(...),
    pin_message: bool = Form(False),
    photo: UploadFile = File(None),
    session: AsyncSession = Depends(get_session)
):
    """
    Maxsus xabar yuborish (to'y, janoza, e'lon va boshqalar)
    """
    try:
        bot = request.app.state.bot

        # Agar rasm yuklangan bo'lsa, uni Telegram ga yuklash
        photo_file_id = None
        if photo and photo.filename:
            # Rasmni botga yuborish (o'zimizga) va file_id olish
            photo_bytes = await photo.read()
            photo_input = BufferedInputFile(photo_bytes, filename=photo.filename or "channel.jpg")

            # Admin ga yoki o'zimizga yuborish va file_id olish
            from config import ADMIN_IDS
            if ADMIN_IDS and len(ADMIN_IDS) > 0 and ADMIN_IDS[0] != 0:
                temp_msg = await bot.send_photo(
                    chat_id=ADMIN_IDS[0],
                    photo=photo_input,
                    caption="⬆️ Kanalga yuklash uchun rasm"
                )
                photo_file_id = temp_msg.photo[-1].file_id

        # Kanallarga yuborish
        posted = await post_custom_message_to_channels(
            bot=bot,
            session=session,
            text=text,
            photo_file_id=photo_file_id,
            pin_message=pin_message
        )

        if not posted:
            raise HTTPException(status_code=400, detail="Hech qaysi kanalga yuborilmadi. Kanallar sozlanganligini tekshiring.")

        return {
            "status": "success",
            "message": f"{len(posted)} ta kanalga yuborildi" + (" va pin qilindi" if pin_message else ""),
            "posted": posted
        }

    except Exception as e:
        logger.error(f"Maxsus post yuborishda xato: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/unpin-all")
async def unpin_all_messages(request: Request, session: AsyncSession = Depends(get_session)):
    """Barcha pin qilingan xabarlarni olib tashlash"""
    try:
        bot = request.app.state.bot
        await unpin_message_from_channels(bot, session)

        return {
            "status": "success",
            "message": "Barcha pin qilingan xabarlar olib tashlandi"
        }

    except Exception as e:
        logger.error(f"Unpin qilishda xato: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test-channel/{channel_id}")
async def test_channel(channel_id: str, request: Request):
    """Kanalni test qilish"""
    try:
        bot = request.app.state.bot
        channel_id_int = int(channel_id)

        # Test xabar yuborish
        msg = await bot.send_message(
            chat_id=channel_id_int,
            text="✅ Test xabari\n\nKanal muvaffaqiyatli ulandi!"
        )

        # Xabarni o'chirish
        await bot.delete_message(chat_id=channel_id_int, message_id=msg.message_id)

        return {
            "status": "success",
            "message": "Kanal ishlayapti! Bot admin sifatida qo'shilgan."
        }

    except Exception as e:
        error_msg = str(e)
        if "bot was kicked" in error_msg or "chat not found" in error_msg:
            return {
                "status": "error",
                "message": "Bot kanalga qo'shilmagan yoki adminlik berilmagan"
            }
        elif "have no rights" in error_msg:
            return {
                "status": "error",
                "message": "Botga xabar yuborish huquqi berilmagan"
            }
        else:
            return {
                "status": "error",
                "message": f"Xato: {error_msg}"
            }
