import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from services.ad_service import get_user, get_user_ads, delete_ad
from services.place_service import get_user_place
from services.supabase_storage_service import media_public_url
from keyboards.keyboards import main_menu, my_ad_actions_keyboard
from config import CATEGORIES

router = Router()
logger = logging.getLogger(__name__)


# =====================================================
# PROFILIM
# =====================================================
@router.message(F.text == "👤 Profilim")
async def profile_handler(message: Message, session: AsyncSession):
    user = await get_user(session, message.from_user.id)
    if not user:
        await message.answer("❌ Avval /start bosing")
        return

    bot_info = await message.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user.referral_code}"

    ads = await get_user_ads(session, user.id)
    active_ads = sum(1 for a in ads if a.status == "active")
    place = await get_user_place(session, user.id)

    text = (
        "👤 <b>Mening profilim</b>\n\n"
        f"📛 Ism: <b>{user.full_name}</b>\n"
        f"🔗 Username: {'@' + user.username if user.username else 'Mavjud emas'}\n"
        f"📞 Telefon: {user.phone or 'Kiritilmagan'}\n"
        f"📅 Ro'yxatdan: {user.created_at.strftime('%d.%m.%Y') if user.created_at else '—'}\n\n"
        f"📝 E'lonlar: <b>{len(ads)} ta</b> ({active_ads} ta faol)\n"
        f"🎯 Qolgan limit: <b>{user.total_ad_limit} ta</b>\n"
        f"🏪 Do'kon: {'✅ ' + place.name if place else '❌ Mavjud emas'}\n\n"
        "🔗 <b>Referal havolangiz:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"👥 Taklif qilganlar: <b>{user.referral_count} ta</b>\n"
        "<i>(Har 5 ta do'st uchun +1 e'lon limiti)</i>"
    )

    await message.answer(
        text,
        parse_mode="HTML",
        disable_web_page_preview=True
    )


# =====================================================
# MENING E'LONLARIM
# =====================================================
@router.message(F.text == "📋 Mening e'lonlarim")
async def my_ads_handler(message: Message, session: AsyncSession):
    user = await get_user(session, message.from_user.id)
    if not user:
        await message.answer("❌ Avval /start bosing")
        return

    ads = await get_user_ads(session, user.id)
    if not ads:
        await message.answer(
            "📋 <b>Sizda hali e'lon yo'q.</b>\n\n"
            "«📝 E'lon joylash» tugmasini bosib yangi e'lon qo'shing!",
            parse_mode="HTML",
            reply_markup=main_menu()
        )
        return

    await message.answer(
        f"📋 <b>Mening e'lonlarim</b> ({len(ads)} ta)\n\n"
        "Har bir e'lon tagidagi tugmalardan foydalaning:",
        parse_mode="HTML"
    )

    for ad in ads[:10]:  # Maksimal 10 ta
        cat_info = CATEGORIES.get(ad.category, {})
        status_icons = {
            "active":   "✅ Faol",
            "pending":  "⏳ Tekshiruvda",
            "rejected": "❌ Rad etildi",
            "expired":  "⌛ Muddati o'tdi"
        }
        status_str = status_icons.get(ad.status, ad.status)

        price_str = f"{float(ad.price):,.0f} {ad.currency}" if ad.price else "Narx yo'q"

        text = (
            f"{cat_info.get('icon', '📦')} <b>{ad.title[:80]}</b>\n"
            f"💰 {price_str} | {status_str}\n"
            f"📅 {ad.created_at.strftime('%d.%m.%Y') if ad.created_at else '—'}"
        )

        images = ad.images if ad.images else []
        try:
            if images:
                media = images[0]
                source = media.telegram_file_id or media_public_url(media)
                if media.media_type == "video":
                    await message.answer_video(
                        video=source,
                        caption=text,
                        parse_mode="HTML",
                        reply_markup=my_ad_actions_keyboard(ad.id),
                    )
                else:
                    await message.answer_photo(
                        photo=source,
                        caption=text,
                        parse_mode="HTML",
                        reply_markup=my_ad_actions_keyboard(ad.id),
                    )
            else:
                await message.answer(
                    text,
                    parse_mode="HTML",
                    reply_markup=my_ad_actions_keyboard(ad.id)
                )
        except Exception as e:
            logger.error(f"E'lon ko'rsatishda xato: {e}")
            await message.answer(
                text,
                parse_mode="HTML",
                reply_markup=my_ad_actions_keyboard(ad.id)
            )


# =====================================================
# E'LON O'CHIRISH
# =====================================================
@router.callback_query(F.data.startswith("delete_ad_"))
async def delete_ad_callback(callback: CallbackQuery, session: AsyncSession):
    ad_id = callback.data.split("delete_ad_")[1]
    user = await get_user(session, callback.from_user.id)
    if not user:
        await callback.answer("Xatolik", show_alert=True)
        return

    deleted = await delete_ad(session, ad_id, user.id)
    if deleted:
        await callback.message.delete()
        await callback.answer("🗑 E'lon o'chirildi!", show_alert=True)
    else:
        await callback.answer("❌ E'lon topilmadi.", show_alert=True)


# =====================================================
# E'LON YANGILASH (MUDDATINI UZAYTIRISH)
# =====================================================
@router.callback_query(F.data.startswith("renew_ad_"))
async def renew_ad_callback(callback: CallbackQuery, session: AsyncSession):
    from sqlalchemy import select
    from database import Ad
    from datetime import datetime, timezone, timedelta
    from config import AD_EXPIRE_DAYS

    ad_id = callback.data.split("renew_ad_")[1]
    user = await get_user(session, callback.from_user.id)

    result = await session.execute(
        select(Ad).where(Ad.id == ad_id, Ad.user_id == user.id)
    )
    ad = result.scalar_one_or_none()

    if not ad:
        await callback.answer("❌ E'lon topilmadi.", show_alert=True)
        return

    if user.total_ad_limit <= 0:
        await callback.answer(
            "⚠️ Limitingiz tugagan! Adminga murojaat qiling.",
            show_alert=True
        )
        return

    ad.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=AD_EXPIRE_DAYS)
    ad.status = "active"
    user.total_ad_limit -= 1
    await session.commit()

    await callback.answer(f"✅ E'lon {AD_EXPIRE_DAYS} kunga uzaytirildi!", show_alert=True)
