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
from keyboards.keyboards import (
    main_menu, phone_keyboard, remove_keyboard, admin_contact_link_keyboard
)
from config import FREE_ADS_PER_USER

router = Router()
logger = logging.getLogger(__name__)


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
        user.total_ad_limit = FREE_ADS_PER_USER
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
            "🏘️ <b>Mahalla Elon</b> botiga xush kelibsiz!\n\n"
            "Bu bot orqali:\n"
            "• 📝 Mahallangizda e'lon joylashingiz\n"
            "• 🏪 Do'kon / choyxona profilingizni oching\n"
            "• 🗺️ Xaritada barcha e'lonlarni ko'ring\n\n"
            "✍️ <b>Boshlash uchun ism va familiyangizni kiriting:</b>",
            parse_mode="HTML",
            reply_markup=remove_keyboard()
        )
        return

    name = user.full_name or message.from_user.full_name
    await message.answer(
        f"👋 Assalomu alaykum, <b>{name}</b>!\n\n"
        "🏘️ <b>Mahalla Elon</b> ga xush kelibsiz!\n"
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
            bonus_msg = ""
            if referrer.referral_count % 5 == 0:
                referrer.total_ad_limit += 1
                bonus_msg = "\n🎁 <b>+1 ta bepul e'lon limiti berildi!</b>"

            try:
                await message.bot.send_message(
                    chat_id=referrer_tg_id,
                    text=(
                        f"👤 <b>Yangi referal!</b>\n\n"
                        f"<b>{full_name}</b> ro'yxatdan o'tdi.\n"
                        f"Jami referallar: <b>{referrer.referral_count} ta</b>"
                        f"{bonus_msg}"
                    ),
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Referal xabar yuborishda xatolik: {e}")
            await session.commit()

    await state.clear()
    await message.answer(
        "🎉 <b>Muvaffaqiyatli ro'yxatdan o'tdingiz!</b>\n\n"
        f"Sizga <b>{FREE_ADS_PER_USER} ta bepul e'lon</b> berildi!\n\n"
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