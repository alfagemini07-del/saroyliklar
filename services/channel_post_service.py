"""
E'lonlarni telegram kanalga avtomatik post qilish xizmati
"""
import logging
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, InputMediaVideo
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import BotSettings, Ad, AdImage
from config import CATEGORIES

logger = logging.getLogger(__name__)


async def post_ad_to_channels(bot: Bot, session: AsyncSession, ad: Ad, user_name: str = None):
    """
    Tasdiqlangan e'lonni kanalga post qilish
    """
    try:
        # BotSettings dan kanallar ro'yxatini olish
        settings_result = await session.execute(select(BotSettings).where(BotSettings.id == 1))
        settings = settings_result.scalar_one_or_none()

        if not settings or not settings.auto_post_to_channel:
            logger.info("Kanal postlash o'chirilgan")
            return

        if not settings.post_channel_ids or len(settings.post_channel_ids) == 0:
            logger.warning("Post qilinadigan kanallar yo'q")
            return

        # E'lon ma'lumotlarini tayyorlash
        cat_info = CATEGORIES.get(ad.category, {})

        # Narx
        price_text = f"💰 <b>Narx:</b> {float(ad.price):,.0f} {ad.currency}" if ad.price else "💰 <b>Narx:</b> Kelishiladi"

        # Manzil
        address_text = f"📍 <b>Manzil:</b> {ad.address}" if ad.address else ""

        # Telefon
        phone_text = f"📞 <b>Telefon:</b> <code>{ad.phone}</code>" if ad.phone else ""

        # Tavsif
        description = ad.description[:300] + "..." if ad.description and len(ad.description) > 300 else ad.description or ""

        # Post matni
        caption = (
            f"{cat_info.get('icon', '📦')} <b>{ad.title}</b>\n\n"
            f"{description}\n\n"
            f"{price_text}\n"
            f"{phone_text}\n"
            f"{address_text}"
        )

        # Inline tugmalar
        buttons = []

        # Telefon tugmasi
        if ad.phone:
            phone_clean = ad.phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
            buttons.append(InlineKeyboardButton(text="📞 Qo'ng'iroq qilish", url=f"tel:{phone_clean}"))

        # Telegram orqali bog'lanish
        if user_name:
            buttons.append(InlineKeyboardButton(text="💬 Yozish", url=f"https://t.me/{user_name}"))

        # Xaritada ko'rish (agar lokatsiya mavjud bo'lsa)
        if ad.lat and ad.lng:
            buttons.append(InlineKeyboardButton(text="📍 Xaritada ko'rish", url=f"https://www.google.com/maps?q={ad.lat},{ad.lng}"))

        keyboard = InlineKeyboardMarkup(inline_keyboard=[buttons] if buttons else [])

        # Rasmlarni olish
        imgs_result = await session.execute(
            select(AdImage).where(AdImage.ad_id == ad.id).order_by(AdImage.order_num).limit(10)
        )
        images = imgs_result.scalars().all()

        # Har bir kanalga post qilish
        for channel_id in settings.post_channel_ids:
            try:
                channel_id_int = int(channel_id) if isinstance(channel_id, str) else channel_id

                if images and len(images) > 0:
                    # Rasmlar bor - media group yoki bitta rasm
                    if len(images) == 1:
                        # Bitta rasm
                        file_id = images[0].telegram_file_id or images[0].public_url or images[0].file_id
                        if file_id:
                            if images[0].media_type == "video":
                                await bot.send_video(
                                    chat_id=channel_id_int,
                                    video=file_id,
                                    caption=caption,
                                    parse_mode="HTML",
                                    reply_markup=keyboard
                                )
                            else:
                                await bot.send_photo(
                                    chat_id=channel_id_int,
                                    photo=file_id,
                                    caption=caption,
                                    parse_mode="HTML",
                                    reply_markup=keyboard
                                )
                    else:
                        # Ko'p rasmlar - media group
                        media = []
                        for i, img in enumerate(images[:10]):  # Max 10 ta
                            file_id = img.telegram_file_id or img.public_url or img.file_id
                            if file_id:
                                media_cls = InputMediaVideo if img.media_type == "video" else InputMediaPhoto
                                if i == 0:
                                    media.append(media_cls(media=file_id, caption=caption, parse_mode="HTML"))
                                else:
                                    media.append(media_cls(media=file_id))

                        if media:
                            await bot.send_media_group(chat_id=channel_id_int, media=media)
                            # Tugmalarni alohida xabar sifatida yuborish
                            if buttons:
                                await bot.send_message(
                                    chat_id=channel_id_int,
                                    text="👆 Yuqoridagi e'lon bilan bog'lanish:",
                                    reply_markup=keyboard
                                )
                        else:
                            # Rasmlar URL bo'lsa
                            await bot.send_message(
                                chat_id=channel_id_int,
                                text=caption + f"\n\n🖼 <i>Rasm: {len(images)} ta</i>",
                                parse_mode="HTML",
                                reply_markup=keyboard
                            )
                else:
                    # Rasmsiz post
                    await bot.send_message(
                        chat_id=channel_id_int,
                        text=caption,
                        parse_mode="HTML",
                        reply_markup=keyboard
                    )

                logger.info(f"E'lon #{ad.id[:8]} kanalga post qilindi: {channel_id}")

            except Exception as e:
                logger.error(f"Kanalga post qilishda xato {channel_id}: {e}")
                continue

    except Exception as e:
        logger.error(f"E'lonni kanalga post qilishda xato: {e}")


async def post_custom_message_to_channels(
    bot: Bot,
    session: AsyncSession,
    text: str,
    photo_file_id: str = None,
    pin_message: bool = False
):
    """
    Admin tomonidan maxsus xabar yuborish (to'y, janoza va boshqalar)
    """
    try:
        # Kanallarni olish
        settings_result = await session.execute(select(BotSettings).where(BotSettings.id == 1))
        settings = settings_result.scalar_one_or_none()

        if not settings or not settings.post_channel_ids:
            logger.warning("Post qilinadigan kanallar yo'q")
            return []

        posted_messages = []

        for channel_id in settings.post_channel_ids:
            try:
                channel_id_int = int(channel_id) if isinstance(channel_id, str) else channel_id

                if photo_file_id and not photo_file_id.startswith('/') and not photo_file_id.startswith('http'):
                    # Rasmli xabar
                    msg = await bot.send_photo(
                        chat_id=channel_id_int,
                        photo=photo_file_id,
                        caption=text,
                        parse_mode="HTML"
                    )
                else:
                    # Matnli xabar
                    msg = await bot.send_message(
                        chat_id=channel_id_int,
                        text=text,
                        parse_mode="HTML"
                    )

                # Pin qilish
                if pin_message:
                    await bot.pin_chat_message(
                        chat_id=channel_id_int,
                        message_id=msg.message_id,
                        disable_notification=True
                    )

                posted_messages.append({
                    "channel_id": channel_id,
                    "message_id": msg.message_id
                })

                logger.info(f"Maxsus xabar kanalga yuborildi: {channel_id}")

            except Exception as e:
                logger.error(f"Maxsus xabarni yuborishda xato {channel_id}: {e}")
                continue

        return posted_messages

    except Exception as e:
        logger.error(f"Maxsus xabar yuborishda xato: {e}")
        return []


async def unpin_message_from_channels(bot: Bot, session: AsyncSession, message_id: int = None):
    """
    Kanaldan xabarni unpin qilish
    """
    try:
        settings_result = await session.execute(select(BotSettings).where(BotSettings.id == 1))
        settings = settings_result.scalar_one_or_none()

        if not settings or not settings.post_channel_ids:
            return

        for channel_id in settings.post_channel_ids:
            try:
                channel_id_int = int(channel_id) if isinstance(channel_id, str) else channel_id

                if message_id:
                    # Ma'lum xabarni unpin qilish
                    await bot.unpin_chat_message(chat_id=channel_id_int, message_id=message_id)
                else:
                    # Barcha xabarlarni unpin qilish
                    await bot.unpin_all_chat_messages(chat_id=channel_id_int)

                logger.info(f"Xabar unpin qilindi: {channel_id}")

            except Exception as e:
                logger.error(f"Xabarni unpin qilishda xato {channel_id}: {e}")
                continue

    except Exception as e:
        logger.error(f"Unpin qilishda xato: {e}")
