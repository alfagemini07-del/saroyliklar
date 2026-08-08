import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from states import Register
from database import User, BotSettings
from services.ad_service import get_user, create_or_update_user
from services.place_service import get_user_place
from keyboards.keyboards import (
    main_menu, phone_keyboard, remove_keyboard, admin_contact_link_keyboard,
    webapp_inline_keyboard,
)
router = Router()
logger = logging.getLogger(__name__)


@router.message(F.text == "🛍 Saroylik bozori")
async def open_marketplace_handler(message: Message):
    await message.answer(
        "Mahalliy do'konlar va mahsulotlarni ochish uchun quyidagi tugmani bosing:",
        reply_markup=webapp_inline_keyboard(),
    )


# =====================================================
# /start BUYRUG'I
# =====================================================
@router.message(CommandStart())
async def start_handler(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    command: CommandObject
):
    await state.clear()

    user = await get_user(session, message.from_user.id)
    is_new_user = False

    if not user:
        is_new_user = True
        user = await create_or_update_user(
            session,
            message.from_user.id,
            message.from_user.full_name,
            message.from_user.username
        )
        await session.commit()

    # Referral tizimi
    if is_new_user and command.args and command.args.startswith("ref_"):
        referrer_code = command.args
        result = await session.execute(
            select(User).where(User.referral_code == referrer_code)
        )
        referrer = result.scalar_one_or_none()

        if referrer and referrer.id != user.id and user.referred_by_id is None:
            user.referred_by_id = referrer.id
            await session.commit()
            await state.update_data(
                referrer_id=referrer.id,
                referrer_telegram_id=referrer.telegram_id
            )

    # Ro'yxatdan o'tmagan foydalanuvchi
    if not user.phone:
        await state.set_state(Register.full_name)
        await message.answer(
            "👋 <b>Assalomu alaykum!</b>\n\n"
            "🛍 <b>Saroylik bozori</b> botiga xush kelibsiz!\n\n"
            "Bu bot orqali:\n"
            "• 🏪 Mahalliy do'konlarni topasiz\n"
            "• 🛒 Mahsulotlar va narxlarni ko'rasiz\n"
            "• 📍 Do'konlarni xaritadan topasiz\n"
            "• 📦 O'z do'koningiz va katalogingizni ochasiz\n\n"
            "✍️ <b>Boshlash uchun ism va familiyangizni kiriting:</b>",
            parse_mode="HTML",
            reply_markup=remove_keyboard()
        )
        return

    name = user.full_name or message.from_user.full_name
    await message.answer(
        f"👋 Assalomu alaykum, <b>{name}</b>!\n\n"
        "🛍 <b>Saroylik bozori</b>ga xush kelibsiz!\n"
        "Quyidagi menyudan foydalaning 👇",
        parse_mode="HTML",
        reply_markup=main_menu()
    )


# =====================================================
# RO'YXATDAN O'TISH — ISM
# =====================================================
@router.message(Register.full_name)
async def register_name_step(message: Message, state: FSMContext):
    if not message.text or len(message.text.strip()) < 2:
        await message.answer(
            "❌ Ism juda qisqa. Iltimos, to'liq ismingizni kiriting:"
        )
        return

    full_name = message.text.strip()
    await state.update_data(full_name=full_name)
    await state.set_state(Register.phone)
    await message.answer(
        f"✅ Rahmat, <b>{full_name}</b>!\n\n"
        "📱 Endi pastdagi <b>«Raqamimni ulashish»</b> tugmasini bosing:",
        parse_mode="HTML",
        reply_markup=phone_keyboard()
    )


# =====================================================
# RO'YXATDAN O'TISH — TELEFON
# =====================================================
@router.message(Register.phone)
async def register_phone_step(
    message: Message,
    state: FSMContext,
    session: AsyncSession
):
    if message.text and message.text == "❌ Bekor qilish":
        await message.answer(
            "⚠️ Ro'yxatdan o'tish majburiy.\n\n"
            "Iltimos, <b>«Raqamimni ulashish»</b> tugmasini bosing:",
            parse_mode="HTML",
            reply_markup=phone_keyboard()
        )
        return

    data = await state.get_data()
    full_name = data.get("full_name", message.from_user.full_name)
    phone = ""

    if message.contact:
        if message.contact.user_id != message.from_user.id:
            await message.answer(
                "⚠️ Iltimos, <b>faqat o'z telefon raqamingizni</b> ulashing!",
                parse_mode="HTML",
                reply_markup=phone_keyboard()
            )
            return
        phone = message.contact.phone_number
    elif message.text:
        import re
        raw = message.text.strip().replace(" ", "").replace("-", "")
        if re.match(r'^\+?998\d{9}$', raw) or re.match(r'^\d{9}$', raw):
            phone = raw
        else:
            await message.answer(
                "❌ <b>Noto'g'ri raqam formati!</b>\n\n"
                "Iltimos, <b>«Raqamimni ulashish»</b> tugmasi orqali yuboring:",
                parse_mode="HTML",
                reply_markup=phone_keyboard()
            )
            return

    if not phone:
        await message.answer(
            "⚠️ Telefon raqam bo'sh. Qayta urinib ko'ring:",
            reply_markup=phone_keyboard()
        )
        return

    user = await get_user(session, message.from_user.id)
    if user:
        user.full_name = full_name
        user.phone = phone
        await session.commit()

    # Referral bonus
    ref_data = await state.get_data()
    referrer_id = ref_data.get("referrer_id")
    referrer_tg_id = ref_data.get("referrer_telegram_id")

    if referrer_id and referrer_tg_id:
        ref_result = await session.execute(select(User).where(User.id == referrer_id))
        referrer = ref_result.scalar_one_or_none()

        if referrer:
            referrer.referral_count += 1
            try:
                await message.bot.send_message(
                    chat_id=referrer_tg_id,
                    text=(
                        f"👤 <b>Yangi referal!</b>\n\n"
                        f"<b>{full_name}</b> ro'yxatdan o'tdi.\n"
                        f"Jami takliflar: <b>{referrer.referral_count} ta</b>"
                    ),
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Referal xabar yuborishda xatolik: {e}")
            await session.commit()

    await state.clear()
    await message.answer(
        "🎉 <b>Muvaffaqiyatli ro'yxatdan o'tdingiz!</b>\n\n"
        "Endi mahalliy do'konlarni ko'rishingiz yoki o'z do'koningizni ochishingiz mumkin.\n\n"
        "Quyidagi menyudan foydalaning 👇",
        parse_mode="HTML",
        reply_markup=main_menu()
    )


# =====================================================
# ADMIN BILAN ALOQA
# =====================================================
@router.message(F.text == "👨‍💻 Aloqa")
async def contact_admin_handler(message: Message, session: AsyncSession):
    result = await session.execute(select(BotSettings).where(BotSettings.id == 1))
    settings = result.scalar_one_or_none()
    admin_link = "https://t.me/admin"
    if settings and settings.admin_contact_link:
        admin_link = settings.admin_contact_link

    await message.answer(
        "📞 <b>Admin bilan aloqa</b>\n\n"
        "Savol yoki muammolaringiz bo'lsa, adminga yozing:",
        parse_mode="HTML",
        reply_markup=admin_contact_link_keyboard(admin_link)
    )


@router.message(F.text == "👤 Profilim")
async def profile_handler(message: Message, session: AsyncSession):
    user = await get_user(session, message.from_user.id)
    if not user:
        await message.answer("❌ Avval /start bosing")
        return

    place = await get_user_place(session, user.id)
    product_count = len(place.photos) if place else 0
    status_names = {
        "active": "✅ Faol",
        "pending": "⏳ Tekshiruvda",
        "rejected": "❌ Rad etilgan",
        "inactive": "⏸ Yopiq",
    }
    store_status = status_names.get(place.status, place.status) if place else "Mavjud emas"
    bot_info = await message.bot.get_me()
    referral_link = f"https://t.me/{bot_info.username}?start={user.referral_code}"

    text = (
        "👤 <b>Mening profilim</b>\n\n"
        f"📛 Ism: <b>{user.full_name}</b>\n"
        f"🔗 Username: {'@' + user.username if user.username else 'Mavjud emas'}\n"
        f"📞 Telefon: {user.phone or 'Kiritilmagan'}\n"
        f"📅 Ro'yxatdan: {user.created_at.strftime('%d.%m.%Y') if user.created_at else '—'}\n\n"
        f"🏪 Do'kon: <b>{place.name if place else 'Mavjud emas'}</b>\n"
        f"📌 Holati: <b>{store_status}</b>\n"
        f"📦 Mahsulotlar: <b>{product_count} ta</b>\n\n"
        "🔗 <b>Taklif havolangiz:</b>\n"
        f"<code>{referral_link}</code>\n\n"
        f"👥 Taklif qilganlar: <b>{user.referral_count} ta</b>"
    )
    await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)
