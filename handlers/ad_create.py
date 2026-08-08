import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from states import CreateAd
from database import User, BotSettings
from services.ad_service import get_user, create_ad, get_stats
from services.ai_service import detect_category
from services.image_storage_service import upload_telegram_media
from keyboards.keyboards import (
    main_menu, cancel_keyboard, skip_cancel_keyboard,
    location_keyboard, categories_keyboard, currency_keyboard,
    ad_confirm_keyboard, admin_ad_approve_keyboard
)
from config import CATEGORIES, MAX_AD_IMAGES, ADMIN_IDS

router = Router()
logger = logging.getLogger(__name__)


# =====================================================
# E'LON JOYLASH — BOSHLASH
# =====================================================
@router.message(F.text == "📝 E'lon joylash")
async def start_create_ad(message: Message, state: FSMContext, session: AsyncSession):
    user = await get_user(session, message.from_user.id)
    if not user:
        await message.answer("❌ Avval /start bosing")
        return

    if not user.phone:
        await message.answer(
            "❌ E'lon joylash uchun avval ro'yxatdan o'ting.\n"
            "/start bosing.",
            reply_markup=main_menu()
        )
        return

    if user.total_ad_limit <= 0:
        await message.answer(
            "⚠️ <b>E'lon limitingiz tugagan!</b>\n\n"
            "Yangi e'lon joylash uchun adminga murojaat qiling.",
            parse_mode="HTML",
            reply_markup=main_menu()
        )
        return

    await state.clear()
    await state.set_state(CreateAd.photos)
    await state.update_data(photos=[], user_id=user.id, phone=user.phone)

    await message.answer(
        "📝 <b>Yangi e'lon joylash</b>\n\n"
        f"📸 <b>1-qadam: Rasm yuklash</b>\n\n"
        f"E'lonizga 1 dan {MAX_AD_IMAGES} tagacha rasm yuboring.\n"
        "Rasmlar yuborib bo'lgach, <b>«✅ Tayyor»</b> ni bosing.\n\n"
        "<i>Rasmsiz ham e'lon joylash mumkin — «⏭ O'tkazib yuborish» ni bosing</i>",
        parse_mode="HTML",
        reply_markup=_photos_keyboard()
    )


def _photos_keyboard():
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Tayyor — rasmlar qabul qilindi")],
            [KeyboardButton(text="⏭ Rasmsiz davom etish")],
            [KeyboardButton(text="❌ Bekor qilish")],
        ],
        resize_keyboard=True
    )


# =====================================================
# 1-QADAM: RASMLAR
# =====================================================
@router.message(CreateAd.photos, F.photo | F.video)
async def ad_receive_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])

    if len(photos) >= MAX_AD_IMAGES:
        await message.answer(
            f"⚠️ Maksimal {MAX_AD_IMAGES} ta rasm yuklash mumkin.\n"
            "«✅ Tayyor» tugmasini bosing."
        )
        return

    file_id = message.photo[-1].file_id if message.photo else message.video.file_id
    photos.append({"file_id": file_id, "type": "image" if message.photo else "video"})
    await state.update_data(photos=photos)

    remaining = MAX_AD_IMAGES - len(photos)
    await message.answer(
        f"✅ Rasm qabul qilindi! ({len(photos)}/{MAX_AD_IMAGES})\n"
        f"{'Yana ' + str(remaining) + ' ta yuklash mumkin. Yoki «✅ Tayyor» ni bosing.' if remaining > 0 else 'Maksimal chegara. «✅ Tayyor» ni bosing.'}",
        reply_markup=_photos_keyboard()
    )


@router.message(CreateAd.photos, F.text.in_(["✅ Tayyor — rasmlar qabul qilindi", "⏭ Rasmsiz davom etish"]))
async def ad_photos_done(message: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    count = len(photos)

    info = f"({count} ta rasm)" if count > 0 else "(rasmsiz)"

    await state.set_state(CreateAd.description)
    await message.answer(
        f"✅ Rasmlar qabul qilindi {info}\n\n"
        "✍️ <b>2-qadam: Tavsif yozish</b>\n\n"
        "E'loningiz haqida qisqacha ma'lumot bering:\n"
        "<i>Misol: «2 xonali kvartira ijaraga beriladi, 5-qavat, kommunal xizmatlar kiritilgan»</i>",
        parse_mode="HTML",
        reply_markup=cancel_keyboard()
    )


# =====================================================
# 2-QADAM: TAVSIF + AI KATEGORIYA ANIQLASH
# =====================================================
@router.message(CreateAd.description)
async def ad_receive_description(message: Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await _cancel_ad(message, state)
        return

    if not message.text or len(message.text.strip()) < 10:
        await message.answer(
            "❌ Tavsif juda qisqa. Kamida 10 ta harf yozing:"
        )
        return

    description = message.text.strip()

    # AI kategoriya aniqlash
    thinking_msg = await message.answer("🤖 AI kategoriya aniqlamoqda...")
    category, confidence = await detect_category(description)
    await thinking_msg.delete()

    await state.update_data(description=description, ai_category=category, ai_confidence=confidence)

    cat_info = CATEGORIES.get(category, {})
    icon = cat_info.get("icon", "📦")
    name = cat_info.get("name", "Boshqa")

    await state.set_state(CreateAd.price)

    await message.answer(
        f"🤖 <b>AI aniqladi:</b> {icon} <b>{name}</b> ({confidence:.0%} aniqlik)\n\n"
        "Agar noto'g'ri bo'lsa, quyidan o'zgartiring:",
        parse_mode="HTML",
        reply_markup=categories_keyboard(selected=category, prefix="adcat")
    )

    await message.answer(
        "💰 <b>3-qadam: Narx</b>\n\n"
        "E'lon narxini kiriting (raqam bilan):\n"
        "<i>Misol: 500000 yoki 450</i>\n\n"
        "Bepul bo'lsa «⏭ O'tkazib yuborish» bosing:",
        parse_mode="HTML",
        reply_markup=skip_cancel_keyboard()
    )


@router.callback_query(F.data.startswith("adcat_"))
async def ad_change_category(callback: CallbackQuery, state: FSMContext):
    category = callback.data.split("adcat_")[1]
    await state.update_data(ai_category=category)
    cat_info = CATEGORIES.get(category, {})

    await callback.message.edit_reply_markup(
        reply_markup=categories_keyboard(selected=category, prefix="adcat")
    )
    await callback.answer(
        f"✅ Kategoriya: {cat_info.get('icon', '')} {cat_info.get('name', '')}"
    )


# =====================================================
# 3-QADAM: NARX
# =====================================================
@router.message(CreateAd.price)
async def ad_receive_price(message: Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await _cancel_ad(message, state)
        return

    if message.text == "⏭ O'tkazib yuborish":
        await state.update_data(price=None, currency="UZS")
        await _ask_location(message, state)
        return

    try:
        price_text = message.text.strip().replace(" ", "").replace(",", "")
        price = float(price_text)
        if price < 0:
            raise ValueError()
    except (ValueError, AttributeError):
        await message.answer(
            "❌ Noto'g'ri narx. Faqat raqam kiriting:\n"
            "<i>Misol: 500000</i>",
            parse_mode="HTML"
        )
        return

    await state.update_data(price=price)

    await message.answer(
        f"💵 <b>Narx:</b> {price:,.0f}\n\n"
        "Qaysi valyutada?",
        parse_mode="HTML",
        reply_markup=currency_keyboard(prefix="adcurrency")
    )


@router.callback_query(F.data.startswith("adcurrency_"))
async def ad_select_currency(callback: CallbackQuery, state: FSMContext):
    currency = callback.data.split("adcurrency_")[1]
    await state.update_data(currency=currency)
    await callback.message.delete()
    await _ask_location(callback.message, state)
    await callback.answer()


async def _ask_location(message: Message, state: FSMContext):
    await state.set_state(CreateAd.location)
    await message.answer(
        "📍 <b>4-qadam: Manzil</b>\n\n"
        "Lokatsiyangizni ulashing yoki manzilni matn sifatida yozing:\n"
        "<i>Misol: «Toshkent, Yunusobod, 12-mavze»</i>\n\n"
        "Yoki lokatsiya tugmasini bosing:",
        parse_mode="HTML",
        reply_markup=location_keyboard()
    )


# =====================================================
# 4-QADAM: LOKATSIYA
# =====================================================
@router.message(CreateAd.location, F.location)
async def ad_receive_location_geo(message: Message, state: FSMContext):
    lat = message.location.latitude
    lng = message.location.longitude
    await state.update_data(lat=lat, lng=lng, address=None)
    await _ask_phone(message, state)


@router.message(CreateAd.location)
async def ad_receive_location_text(message: Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await _cancel_ad(message, state)
        return

    if message.text == "⏭ O'tkazib yuborish":
        await state.update_data(lat=None, lng=None, address=None)
    else:
        await state.update_data(lat=None, lng=None, address=message.text.strip())

    await _ask_phone(message, state)


async def _ask_phone(message: Message, state: FSMContext):
    await state.set_state(CreateAd.phone)
    await message.answer(
        "📞 <b>5-qadam: Aloqa raqami</b>\n\n"
        "E'lon uchun telefon raqamingizni kiriting\n"
        "(Profildagi raqamingiz avtomatik ishlatilishi uchun «⏭ O'tkazib yuborish» bosing):",
        parse_mode="HTML",
        reply_markup=skip_cancel_keyboard()
    )


# =====================================================
# 5-QADAM: TELEFON
# =====================================================
@router.message(CreateAd.phone)
async def ad_receive_phone(message: Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await _cancel_ad(message, state)
        return

    data = await state.get_data()

    if message.text == "⏭ O'tkazib yuborish":
        phone = data.get("phone", "")
    else:
        phone = message.text.strip()

    await state.update_data(ad_phone=phone)
    await state.set_state(CreateAd.confirm)

    # Ko'rinish
    await _show_ad_preview(message, state)


async def _show_ad_preview(message: Message, state: FSMContext):
    data = await state.get_data()
    category = data.get("ai_category", "other")
    cat_info = CATEGORIES.get(category, {})

    price_str = ""
    if data.get("price"):
        price_str = f"\n💰 Narx: <b>{float(data['price']):,.0f} {data.get('currency', 'UZS')}</b>"

    address_str = ""
    if data.get("address"):
        address_str = f"\n📍 Manzil: {data['address']}"
    elif data.get("lat"):
        address_str = f"\n📍 GPS lokatsiya ulangan"

    phone_str = f"\n📞 Tel: {data.get('ad_phone', '')}" if data.get('ad_phone') else ""
    photos_count = len(data.get("photos", []))

    preview = (
        "👁 <b>Ko'rinish (Preview):</b>\n\n"
        f"{cat_info.get('icon', '📦')} <b>{cat_info.get('name', 'Boshqa')}</b>\n"
        f"📝 {data.get('description', '')}"
        f"{price_str}"
        f"{address_str}"
        f"{phone_str}\n"
        f"📸 Rasmlar: {photos_count} ta\n\n"
        "✅ Joylashtirishamizmi?"
    )

    await message.answer(preview, parse_mode="HTML", reply_markup=ad_confirm_keyboard())


# =====================================================
# 6-QADAM: TASDIQLASH
# =====================================================
@router.callback_query(CreateAd.confirm, F.data == "ad_confirm_yes")
async def ad_confirm_submit(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    user = await get_user(session, callback.from_user.id)

    if not user:
        await callback.answer("Xatolik. /start bosing.", show_alert=True)
        return

    # Settings: tasdiqlash kerakmi?
    settings_result = await session.execute(
        select(BotSettings).where(BotSettings.id == 1)
    )
    settings = settings_result.scalar_one_or_none()
    require_approval = settings.require_approval if settings else True

    # Media fayllarni Supabase Storage'ga yuklash.
    photos = data.get("photos", [])
    stored_media = []
    for media in photos:
        file_id = media["file_id"] if isinstance(media, dict) else media
        stored = await upload_telegram_media(callback.bot, file_id, prefix="bot-ad")
        stored.telegram_file_id = file_id
        stored_media.append(stored)

    ad = await create_ad(
        session=session,
        user_id=user.id,
        title=data.get("description", "")[:100],
        description=data.get("description", ""),
        category=data.get("ai_category", "other"),
        price=data.get("price"),
        currency=data.get("currency", "UZS"),
        lat=data.get("lat"),
        lng=data.get("lng"),
        phone=data.get("ad_phone") or user.phone,
        address=data.get("address"),
        ai_confidence=data.get("ai_confidence"),
        media_items=stored_media,
        require_approval=require_approval
    )

    # Limitni kamaytirish
    user.total_ad_limit -= 1
    await session.commit()

    await state.clear()
    await callback.message.delete()

    if require_approval:
        await callback.message.answer(
            "✅ <b>E'lon yuborildi!</b>\n\n"
            "⏳ Admin tekshirib, tez orada tasdiqlanadi.\n"
            f"Qolgan limitingiz: <b>{user.total_ad_limit} ta</b>",
            parse_mode="HTML",
            reply_markup=main_menu()
        )

        # Adminga xabar yuborish
        await _notify_admins_new_ad(callback.bot, ad, user)
    else:
        await callback.message.answer(
            "✅ <b>E'lon muvaffaqiyatli joylashtirildi!</b>\n\n"
            f"Qolgan limitingiz: <b>{user.total_ad_limit} ta</b>",
            parse_mode="HTML",
            reply_markup=main_menu()
        )
    await callback.answer()


@router.callback_query(CreateAd.confirm, F.data == "ad_confirm_edit")
async def ad_confirm_edit(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CreateAd.photos)
    await state.update_data(photos=[])
    await callback.message.delete()
    await callback.message.answer(
        "♻️ Qaytadan boshlaymiz.\n"
        "📸 Yangi rasmlar yuboring yoki o'tkazib yuboring:",
        reply_markup=_photos_keyboard()
    )
    await callback.answer()


@router.callback_query(CreateAd.confirm, F.data == "ad_confirm_no")
async def ad_confirm_no(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.message.answer("❌ E'lon bekor qilindi.", reply_markup=main_menu())
    await callback.answer()


# =====================================================
# ADMINGA E'LON HAQIDA XABAR YUBORISH
# =====================================================
async def _notify_admins_new_ad(bot, ad, user):
    from config import ADMIN_IDS, CATEGORIES
    cat_info = CATEGORIES.get(ad.category, {})

    price_str = f"{float(ad.price):,.0f} {ad.currency}" if ad.price else "Ko'rsatilmagan"
    text = (
        f"📢 <b>Yangi e'lon tekshiruvga keldi!</b>\n\n"
        f"{cat_info.get('icon', '📦')} <b>{cat_info.get('name', '')}</b>\n"
        f"📝 {ad.description[:200]}\n"
        f"💰 Narx: {price_str}\n"
        f"📞 Tel: {ad.phone or 'Mavjud emas'}\n\n"
        f"👤 Foydalanuvchi: <b>{user.full_name}</b> (@{user.username or 'Mavjud emas'})\n"
        f"🆔 E'lon ID: <code>{ad.id[:8]}</code>"
    )

    from keyboards.keyboards import admin_ad_approve_keyboard
    kb = admin_ad_approve_keyboard(ad.id)

    for admin_id in ADMIN_IDS:
        if admin_id == 0:
            continue
        try:
            images = ad.images if ad.images else []
            if images and images[0].telegram_file_id:
                file_id = images[0].telegram_file_id
                if images[0].media_type == "video":
                    await bot.send_video(
                        chat_id=admin_id,
                        video=file_id,
                        caption=text,
                        parse_mode="HTML",
                        reply_markup=kb,
                    )
                else:
                    await bot.send_photo(
                        chat_id=admin_id,
                        photo=file_id,
                        caption=text,
                        parse_mode="HTML",
                        reply_markup=kb
                    )
            else:
                    await bot.send_message(
                        chat_id=admin_id,
                        text=text + "\n\n<i>Media Web App orqali yuklangan</i>",
                        parse_mode="HTML",
                        reply_markup=kb
                    )
        except Exception as e:
            logger.error(f"Adminga xabar yuborishda xato ({admin_id}): {e}")


# =====================================================
# YORDAMCHI FUNKSIYA
# =====================================================
async def _cancel_ad(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ E'lon bekor qilindi.", reply_markup=main_menu())
