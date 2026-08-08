import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from states import CreatePlace, AddPlacePhoto
from database import User, BotSettings
from services.ad_service import get_user
from services.place_service import (
    create_place, get_user_place, get_place,
    add_place_photo, delete_place_photo, update_place, delete_place
)
from services.image_storage_service import upload_telegram_media
from keyboards.keyboards import (
    main_menu, cancel_keyboard, skip_cancel_keyboard,
    location_keyboard, categories_keyboard, place_actions_keyboard
)
from config import CATEGORIES, MAX_PLACE_PHOTOS

router = Router()
logger = logging.getLogger(__name__)


# =====================================================
# DO'KON OCHISH — BOSHLASH
# =====================================================
@router.message(F.text == "🏪 Do'kon ochish")
async def start_create_place(message: Message, state: FSMContext, session: AsyncSession):
    user = await get_user(session, message.from_user.id)
    if not user or not user.phone:
        await message.answer("❌ Avval /start bosing va ro'yxatdan o'ting.")
        return

    existing = await get_user_place(session, user.id)
    if existing:
        await _show_my_place(message, existing)
        return

    await state.clear()
    await state.set_state(CreatePlace.name)
    await state.update_data(user_id=user.id)

    await message.answer(
        "🏪 <b>Do'kon / Profil yaratish</b>\n\n"
        "Bu yerda siz mahallangizda:\n"
        "• 🍽️ Restoran / Choyxona / Kafe\n"
        "• 🛒 Do'kon / Bozor\n"
        "• 💼 Xizmatlar shaxobchasi\n"
        "• 🏠 Va boshqa biznесingizni ochishingiz mumkin!\n\n"
        "🏷️ <b>1-qadam: Do'koningiz nomini kiriting:</b>\n"
        "<i>Misol: «Aziz Choyxonasi» yoki «Sarvar Supermarket»</i>",
        parse_mode="HTML",
        reply_markup=cancel_keyboard()
    )


async def _show_my_place(message: Message, place):
    cat_info = CATEGORIES.get(place.category, {})
    verified = "✅ Tasdiqlangan" if place.is_verified else "⏳ Tasdiqlanmagan"
    photos_count = len(place.photos) if place.photos else 0

    text = (
        f"🏪 <b>Sizning profilingiz:</b>\n\n"
        f"🏷️ <b>{place.name}</b> {verified}\n"
        f"{cat_info.get('icon', '📦')} {cat_info.get('name', '')}\n"
        f"📞 {place.phone}\n"
        f"📍 {place.address or 'Manzil kiritilmagan'}\n"
        f"⏰ {place.working_hours or 'Ish vaqti kiritilmagan'}\n"
        f"🖼 Galerеya: {photos_count} ta rasm\n\n"
        f"Quyidagi tugmalardan foydalaning:"
    )

    from keyboards.keyboards import place_actions_keyboard
    await message.answer(text, parse_mode="HTML", reply_markup=place_actions_keyboard(place.id))


# =====================================================
# 1-QADAM: NOMI
# =====================================================
@router.message(CreatePlace.name)
async def place_receive_name(message: Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await _cancel_place(message, state)
        return

    if not message.text or len(message.text.strip()) < 2:
        await message.answer("❌ Nom juda qisqa. Kamida 2 ta harf kiriting:")
        return

    await state.update_data(name=message.text.strip())
    await state.set_state(CreatePlace.category)

    await message.answer(
        "🏷️ <b>2-qadam: Kategoriya tanlang</b>\n\n"
        "Do'koningiz qaysi sohada?",
        parse_mode="HTML",
        reply_markup=categories_keyboard(prefix="plcat")
    )


# =====================================================
# 2-QADAM: KATEGORIYA
# =====================================================
@router.callback_query(CreatePlace.category, F.data.startswith("plcat_"))
async def place_receive_category(callback: CallbackQuery, state: FSMContext):
    category = callback.data.split("plcat_")[1]
    await state.update_data(category=category)
    cat_info = CATEGORIES.get(category, {})

    await callback.message.delete()
    await state.set_state(CreatePlace.phone)

    await callback.message.answer(
        f"✅ Kategoriya: {cat_info.get('icon', '')} <b>{cat_info.get('name', '')}</b>\n\n"
        "📞 <b>3-qadam: Aloqa raqami</b>\n\n"
        "Mijozlar siz bilan bog'lanishlari uchun telefon raqamingizni kiriting:",
        parse_mode="HTML",
        reply_markup=cancel_keyboard()
    )
    await callback.answer()


# =====================================================
# 3-QADAM: TELEFON
# =====================================================
@router.message(CreatePlace.phone)
async def place_receive_phone(message: Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await _cancel_place(message, state)
        return

    import re
    raw = message.text.strip().replace(" ", "").replace("-", "") if message.text else ""
    if not (re.match(r'^\+?998\d{9}$', raw) or re.match(r'^\d{9,15}$', raw)):
        await message.answer(
            "❌ Noto'g'ri raqam formati.\n"
            "Misol: <code>+998901234567</code>",
            parse_mode="HTML"
        )
        return

    await state.update_data(phone=message.text.strip())
    await state.set_state(CreatePlace.description)

    await message.answer(
        "📝 <b>4-qadam: Tavsif</b>\n\n"
        "Do'koningiz haqida qisqacha ma'lumot bering:\n"
        "<i>Misol: «Kechagacha ishlaymiz. Yangi va toza mahsulotlar. Narxlar bozordan arzon!»</i>\n\n"
        "O'tkazib yuborish mumkin:",
        parse_mode="HTML",
        reply_markup=skip_cancel_keyboard()
    )


# =====================================================
# 4-QADAM: TAVSIF
# =====================================================
@router.message(CreatePlace.description)
async def place_receive_description(message: Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await _cancel_place(message, state)
        return

    desc = "" if message.text == "⏭ O'tkazib yuborish" else message.text.strip()
    await state.update_data(description=desc)
    await state.set_state(CreatePlace.avatar)

    await message.answer(
        "🖼 <b>5-qadam: Profil rasmi (Avatar)</b>\n\n"
        "Do'koningizning logosi yoki asosiy rasmini yuboring.\n"
        "Bu rasm xaritada va galеrеyada ko'rinadi.\n\n"
        "O'tkazib yuborish mumkin:",
        parse_mode="HTML",
        reply_markup=skip_cancel_keyboard()
    )


# =====================================================
# 5-QADAM: AVATAR
# =====================================================
@router.message(CreatePlace.avatar, F.photo)
async def place_receive_avatar(message: Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    await state.update_data(avatar_file_id=file_id)
    await state.set_state(CreatePlace.cover)
    await message.answer(
        "✅ Avatar qabul qilindi!\n\n"
        "🖼 <b>6-qadam: Cover (Banner rasm)</b>\n\n"
        "Profilingiz yuqorisida ko'rinadigan keng rasm.\n"
        "O'tkazib yuborish mumkin:",
        parse_mode="HTML",
        reply_markup=skip_cancel_keyboard()
    )


@router.message(CreatePlace.avatar)
async def place_avatar_skip(message: Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await _cancel_place(message, state)
        return
    await state.update_data(avatar_file_id=None)
    await state.set_state(CreatePlace.cover)
    await message.answer(
        "🖼 <b>6-qadam: Cover (Banner rasm)</b>\n\n"
        "Keng banner rasm (ixtiyoriy).\n"
        "O'tkazib yuborish mumkin:",
        parse_mode="HTML",
        reply_markup=skip_cancel_keyboard()
    )


# =====================================================
# 6-QADAM: COVER
# =====================================================
@router.message(CreatePlace.cover, F.photo)
async def place_receive_cover(message: Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    await state.update_data(cover_file_id=file_id)
    await state.set_state(CreatePlace.location)
    await _ask_place_location(message)


@router.message(CreatePlace.cover)
async def place_cover_skip(message: Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await _cancel_place(message, state)
        return
    await state.update_data(cover_file_id=None)
    await state.set_state(CreatePlace.location)
    await _ask_place_location(message)


async def _ask_place_location(message: Message):
    await message.answer(
        "📍 <b>7-qadam: Manzil</b>\n\n"
        "Do'koningiz joylashgan manzilni kiriting yoki lokatsiya ulashing:\n"
        "<i>Misol: «Toshkent, Yunusobod tumani, Navruz ko'chasi 5-uy»</i>",
        parse_mode="HTML",
        reply_markup=location_keyboard()
    )


# =====================================================
# 7-QADAM: LOKATSIYA
# =====================================================
@router.message(CreatePlace.location, F.location)
async def place_receive_location_geo(message: Message, state: FSMContext):
    await state.update_data(
        lat=message.location.latitude,
        lng=message.location.longitude,
        address=None
    )
    await state.set_state(CreatePlace.hours)
    await _ask_place_hours(message)


@router.message(CreatePlace.location)
async def place_receive_location_text(message: Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await _cancel_place(message, state)
        return
    if message.text == "⏭ O'tkazib yuborish":
        await state.update_data(lat=None, lng=None, address=None)
    else:
        await state.update_data(lat=None, lng=None, address=message.text.strip())
    await state.set_state(CreatePlace.hours)
    await _ask_place_hours(message)


async def _ask_place_hours(message: Message):
    await message.answer(
        "⏰ <b>8-qadam: Ish vaqti</b>\n\n"
        "Do'koningiz qachon ishlaydi?\n"
        "<i>Misol: «09:00 - 22:00» yoki «24 soat»</i>\n\n"
        "O'tkazib yuborish mumkin:",
        parse_mode="HTML",
        reply_markup=skip_cancel_keyboard()
    )


# =====================================================
# 8-QADAM: ISH VAQTI
# =====================================================
@router.message(CreatePlace.hours)
async def place_receive_hours(message: Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await _cancel_place(message, state)
        return
    hours = "" if message.text == "⏭ O'tkazib yuborish" else message.text.strip()
    await state.update_data(working_hours=hours)
    await state.set_state(CreatePlace.social)

    await message.answer(
        "📱 <b>9-qadam: Ijtimoiy tarmoqlar (ixtiyoriy)</b>\n\n"
        "Telegram va Instagram usernamingizni kiriting:\n"
        "<i>Misol: <code>@dokonim_uz</code></i>\n\n"
        "Ikkisini alohida qatordan yozing yoki o'tkazib yuboring.",
        parse_mode="HTML",
        reply_markup=skip_cancel_keyboard()
    )


# =====================================================
# 9-QADAM: IJTIMOIY TARMOQLAR
# =====================================================
@router.message(CreatePlace.social)
async def place_receive_social(message: Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await _cancel_place(message, state)
        return

    telegram_link = None
    instagram_link = None

    if message.text and message.text != "⏭ O'tkazib yuborish":
        lines = message.text.strip().split("\n")
        for line in lines:
            line = line.strip()
            if "t.me" in line or line.startswith("@"):
                telegram_link = line.replace("https://t.me/", "@")
            elif "instagram" in line:
                instagram_link = line
            elif "@" in line:
                if not telegram_link:
                    telegram_link = line

    await state.update_data(telegram=telegram_link, instagram=instagram_link)
    await state.set_state(CreatePlace.confirm)

    # Preview ko'rsatish
    data = await state.get_data()
    await _show_place_preview(message, data)


# =====================================================
# 10-QADAM: TASDIQLASH
# =====================================================
async def _show_place_preview(message: Message, data: dict):
    cat_info = CATEGORIES.get(data.get("category", "other"), {})
    has_avatar = "✅ Ha" if data.get("avatar_file_id") else "❌ Yo'q"
    has_cover = "✅ Ha" if data.get("cover_file_id") else "❌ Yo'q"

    address_str = ""
    if data.get("address"):
        address_str = f"\n📍 {data['address']}"
    elif data.get("lat"):
        address_str = "\n📍 GPS lokatsiya ulangan"

    social_str = ""
    if data.get("telegram"):
        social_str += f"\n📱 Telegram: {data['telegram']}"
    if data.get("instagram"):
        social_str += f"\n📷 Instagram: {data['instagram']}"

    preview = (
        "👁 <b>Profil ko'rinishi:</b>\n\n"
        f"🏷️ <b>{data.get('name', '')}</b>\n"
        f"{cat_info.get('icon', '📦')} {cat_info.get('name', '')}\n"
        f"📞 {data.get('phone', '')}\n"
        f"📝 {data.get('description', '') or 'Tavsif kiritilmagan'}\n"
        f"{address_str}\n"
        f"⏰ {data.get('working_hours', '') or 'Ish vaqti kiritilmagan'}\n"
        f"{social_str}\n\n"
        f"🖼 Avatar: {has_avatar}\n"
        f"🖼 Cover: {has_cover}\n\n"
        "✅ Profilni saqlashimizmi?"
    )

    from keyboards.keyboards import ad_confirm_keyboard
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Saqlash",        callback_data="place_confirm_yes")
    kb.button(text="❌ Bekor qilish",   callback_data="place_confirm_no")
    kb.adjust(2)

    await message.answer(preview, parse_mode="HTML", reply_markup=kb.as_markup())


@router.callback_query(CreatePlace.confirm, F.data == "place_confirm_yes")
async def place_confirm_submit(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    user = await get_user(session, callback.from_user.id)
    if not user:
        await callback.answer("Xatolik", show_alert=True)
        return

    # Avatar va cover rasmlarini yuklash
    avatar_file_id = data.get("avatar_file_id")
    cover_file_id = data.get("cover_file_id")

    avatar_url = None
    cover_url = None
    avatar_storage_path = None
    cover_storage_path = None

    if avatar_file_id:
        stored_avatar = await upload_telegram_media(callback.bot, avatar_file_id, prefix="bot-place-avatar")
        avatar_storage_path = stored_avatar.file_id
        avatar_url = stored_avatar.public_url

    if cover_file_id:
        stored_cover = await upload_telegram_media(callback.bot, cover_file_id, prefix="bot-place-cover")
        cover_storage_path = stored_cover.file_id
        cover_url = stored_cover.public_url

    place = await create_place(
        session=session,
        user_id=user.id,
        name=data.get("name", ""),
        category=data.get("category", "other"),
        phone=data.get("phone", ""),
        description=data.get("description"),
        lat=data.get("lat"),
        lng=data.get("lng"),
        address=data.get("address"),
        avatar_file_id=avatar_storage_path,
        avatar_url=avatar_url,
        cover_file_id=cover_storage_path,
        cover_url=cover_url,
        working_hours=data.get("working_hours"),
        telegram=data.get("telegram"),
        instagram=data.get("instagram")
    )

    await state.clear()
    await callback.message.delete()

    cat_info = CATEGORIES.get(place.category, {})
    await callback.message.answer(
        f"✅ <b>{place.name}</b> profili tekshiruvga yuborildi!\n\n"
        f"{cat_info.get('icon', '')} {cat_info.get('name', '')}\n\n"
        f"⏳ Admin tasdiqlagach xarita va ro'yxatda ko'rinadi.\n"
        f"📸 Hozirdanoq galereya rasmlarini qo'shishingiz mumkin.\n"
        "Har bir rasm uchun narx va tavsif qo'shishingiz mumkin.",
        parse_mode="HTML",
        reply_markup=place_actions_keyboard(place.id)
    )
    await callback.answer()


@router.callback_query(CreatePlace.confirm, F.data == "place_confirm_no")
async def place_confirm_no(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.message.answer("❌ Profil yaratish bekor qilindi.", reply_markup=main_menu())
    await callback.answer()


# =====================================================
# DO'KON PROFILIGA RASM QO'SHISH
# =====================================================
@router.callback_query(F.data.startswith("add_photo_"))
async def start_add_photo(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    place_id = callback.data.split("add_photo_")[1]
    user = await get_user(session, callback.from_user.id)
    place = await get_place(session, place_id)

    if not place or place.user_id != user.id:
        await callback.answer("❌ Ruxsat yo'q", show_alert=True)
        return

    photos_count = len(place.photos) if place.photos else 0
    if photos_count >= MAX_PLACE_PHOTOS:
        await callback.answer(
            f"❌ Maksimal {MAX_PLACE_PHOTOS} ta rasm joylash mumkin.",
            show_alert=True
        )
        return

    await state.set_state(AddPlacePhoto.photo)
    await state.update_data(place_id=place_id)
    await callback.message.answer(
        f"📸 Rasm yuboring:\n"
        f"({photos_count}/{MAX_PLACE_PHOTOS} ta rasm yuklangan)",
        reply_markup=cancel_keyboard()
    )
    await callback.answer()


@router.message(AddPlacePhoto.photo, F.photo)
async def add_photo_receive(message: Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    await state.update_data(photo_file_id=file_id)
    await state.set_state(AddPlacePhoto.caption)

    await message.answer(
        "✅ Rasm qabul qilindi!\n\n"
        "Ushbu mahsulot/xizmat haqida qisqa izoh yozing\n"
        "<i>Misol: «Lag'mon — 25,000 so'm»</i>\n\n"
        "O'tkazib yuborish mumkin:",
        parse_mode="HTML",
        reply_markup=skip_cancel_keyboard()
    )


@router.message(AddPlacePhoto.caption)
async def add_photo_caption(message: Message, state: FSMContext, session: AsyncSession):
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("❌ Bekor qilindi.", reply_markup=main_menu())
        return

    data = await state.get_data()
    caption = "" if message.text == "⏭ O'tkazib yuborish" else message.text.strip()

    # Rasmni yuklash
    photo_file_id = data["photo_file_id"]
    stored_photo = await upload_telegram_media(message.bot, photo_file_id, prefix="bot-place-product")

    photo = await add_place_photo(
        session=session,
        place_id=data["place_id"],
        file_id=stored_photo.file_id,
        public_url=stored_photo.public_url,
        telegram_file_id=photo_file_id,
        mime_type=stored_photo.mime_type,
        media_type=stored_photo.media_type,
        size_bytes=stored_photo.size_bytes,
        caption=caption
    )

    await state.clear()
    place = await get_place(session, data["place_id"])
    photos_count = len(place.photos) if place.photos else 0

    await message.answer(
        f"✅ Rasm qo'shildi! Jami: {photos_count} ta",
        reply_markup=place_actions_keyboard(data["place_id"])
    )


# =====================================================
# YORDAMCHI FUNKSIYALAR
# =====================================================
async def _cancel_place(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Bekor qilindi.", reply_markup=main_menu())
