import logging
import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from aiogram.exceptions import TelegramRetryAfter

from config import ADMIN_IDS, CATEGORIES
from services.ad_service import get_stats, get_user, approve_ad, reject_ad
from services.place_service import update_place
from services.channel_post_service import post_ad_to_channels
from database import User, Ad, Place
from states import AdminBroadcast
from keyboards.keyboards import main_menu, admin_panel_keyboard

router = Router()
logger = logging.getLogger(__name__)


def is_admin(telegram_id: int) -> bool:
    return telegram_id in ADMIN_IDS


# =====================================================
# ADMIN PANEL
# =====================================================
@router.message(Command("admin"))
async def admin_panel(message: Message, session: AsyncSession):
    if not is_admin(message.from_user.id):
        return

    await message.answer(
        "👨‍💻 <b>Admin Panelga xush kelibsiz!</b>\n\n"
        "Quyidagi menyudan kerakli bo'limni tanlang:",
        parse_mode="HTML",
        reply_markup=admin_panel_keyboard()
    )


@router.callback_query(F.data == "admin_stats")
async def admin_stats_callback(callback: CallbackQuery, session: AsyncSession):
    if not is_admin(callback.from_user.id):
        return

    stats = await get_stats(session)
    text = (
        "📊 <b>Umumiy Statistika</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{stats['total_users']}</b> ta\n"
        f"📝 Jami e'lonlar: <b>{stats['total_ads']}</b> ta\n"
        f"✅ Faol e'lonlar: <b>{stats['active_ads']}</b> ta\n"
        f"⏳ Kutayotganlar: <b>{stats['pending_ads']}</b> ta\n"
        f"🏪 Do'konlar: <b>{stats['total_places']}</b> ta\n"
        f"🚫 Bloklangan: <b>{stats['blocked_users']}</b> ta"
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=admin_panel_keyboard())
    await callback.answer()


@router.callback_query(F.data == "admin_help")
async def admin_help_callback(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    text = (
        "⚙️ <b>Boshqaruv Qo'llanmasi</b>\n\n"
        "🚫 Bloklash: <code>/block TELEGRAM_ID</code>\n"
        "🔓 Blokdan chiqarish: <code>/unblock TELEGRAM_ID</code>\n"
        "🗑 E'lonni o'chirish: <code>/delad ELON_ID</code>\n"
        "🏪 Do'konni o'chirish: <code>/delplace DO'KON_ID</code>\n\n"
        "<i>E'lonlarni tasdiqlash uchun foydalanuvchi e'lon joylaganda "
        "sizga avtomatik xabar keladi.</i>"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=admin_panel_keyboard())
    await callback.answer()


# =====================================================
# E'LON TASDIQLASH / RAD ETISH
# =====================================================
@router.callback_query(F.data.startswith("approve_ad_"))
async def approve_ad_callback(callback: CallbackQuery, session: AsyncSession):
    if not is_admin(callback.from_user.id):
        return

    ad_id = callback.data.split("approve_ad_")[1]
    ad = await approve_ad(session, ad_id)

    if not ad:
        await callback.answer("❌ E'lon topilmadi", show_alert=True)
        return

    cat_info = CATEGORIES.get(ad.category, {})
    await callback.message.edit_caption(
        caption=f"✅ <b>E'lon tasdiqlandi!</b>\n"
                f"{cat_info.get('icon', '')} {ad.title[:100]}",
        parse_mode="HTML"
    )

    # Foydalanuvchiga xabar
    result = await session.execute(select(User).where(User.id == ad.user_id))
    user = result.scalar_one_or_none()
    user_username = user.username if user else None

    try:
        if user:
            await callback.bot.send_message(
                chat_id=user.telegram_id,
                text=(
                    f"✅ <b>E'loningiz tasdiqlandi!</b>\n\n"
                    f"📝 <b>{ad.title[:100]}</b>\n\n"
                    f"E'loningiz endi xaritada ko'rinadi! 🗺️"
                ),
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"Foydalanuvchiga xabar: {e}")

    # Kanalga avtomatik post qilish
    try:
        await post_ad_to_channels(callback.bot, session, ad, user_username)
        logger.info(f"E'lon #{ad.id[:8]} kanallarga post qilindi")
    except Exception as e:
        logger.error(f"Kanalga post qilishda xato: {e}")

    await callback.answer("✅ Tasdiqlandi!")


@router.callback_query(F.data.startswith("reject_ad_"))
async def reject_ad_callback(callback: CallbackQuery, session: AsyncSession):
    if not is_admin(callback.from_user.id):
        return

    ad_id = callback.data.split("reject_ad_")[1]
    ad = await reject_ad(session, ad_id)

    if not ad:
        await callback.answer("❌ E'lon topilmadi", show_alert=True)
        return

    await callback.message.edit_caption(
        caption=f"❌ <b>E'lon rad etildi!</b>\n{ad.title[:100]}",
        parse_mode="HTML"
    )

    # Foydalanuvchiga xabar + limit qaytarish
    try:
        result = await session.execute(select(User).where(User.id == ad.user_id))
        user = result.scalar_one_or_none()
        if user:
            user.total_ad_limit += 1
            await session.commit()
            await callback.bot.send_message(
                chat_id=user.telegram_id,
                text=(
                    "❌ <b>E'loningiz rad etildi.</b>\n\n"
                    "Sabab: Qoidalarga mos kelmagan.\n"
                    "Admin bilan bog'laning: /start → Aloqa"
                ),
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"Foydalanuvchiga xabar: {e}")

    await callback.answer("❌ Rad etildi")


# =====================================================
# DO'KON TASDIQLASH / VERIFIKATSIYA
# =====================================================
@router.callback_query(F.data.startswith("approve_place_"))
async def approve_place_callback(callback: CallbackQuery, session: AsyncSession):
    if not is_admin(callback.from_user.id):
        return

    place_id = callback.data.split("approve_place_")[1]
    place = await update_place(session, place_id, status="active")

    if not place:
        await callback.answer("❌ Do'kon topilmadi", show_alert=True)
        return

    await callback.message.edit_text(
        f"✅ <b>{place.name}</b> faollashtirildi!",
        parse_mode="HTML"
    )
    await callback.answer("✅ Faollashtirildi!")


@router.callback_query(F.data.startswith("verify_place_"))
async def verify_place_callback(callback: CallbackQuery, session: AsyncSession):
    if not is_admin(callback.from_user.id):
        return

    place_id = callback.data.split("verify_place_")[1]
    place = await update_place(session, place_id, is_verified=True, status="active")

    if not place:
        await callback.answer("❌ Topilmadi", show_alert=True)
        return

    await callback.message.edit_text(
        f"⭐ <b>{place.name}</b> verifikatsiya qilindi!",
        parse_mode="HTML"
    )
    await callback.answer("⭐ Verifikatsiya!")


# =====================================================
# FOYDALANUVCHI BLOKLASH
# =====================================================
@router.message(Command("block"))
async def block_user_cmd(message: Message, session: AsyncSession):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("⚠️ Format: <code>/block 123456789</code>", parse_mode="HTML")
        return

    try:
        target_id = int(parts[1])
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer("❌ Foydalanuvchi topilmadi.")
            return

        user.is_blocked = True
        await session.commit()
        await message.answer(
            f"✅ <b>{user.full_name}</b> (ID: {target_id}) bloklandi.",
            parse_mode="HTML"
        )
    except ValueError:
        await message.answer("❌ ID faqat raqamlardan iborat bo'lishi kerak.")


@router.message(Command("unblock"))
async def unblock_user_cmd(message: Message, session: AsyncSession):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("⚠️ Format: <code>/unblock 123456789</code>", parse_mode="HTML")
        return

    try:
        target_id = int(parts[1])
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer("❌ Foydalanuvchi topilmadi.")
            return

        user.is_blocked = False
        await session.commit()
        await message.answer(
            f"✅ <b>{user.full_name}</b> blokdan chiqarildi.",
            parse_mode="HTML"
        )
    except ValueError:
        await message.answer("❌ ID raqamlardan iborat bo'lishi kerak.")


# =====================================================
# E'LON / DO'KON O'CHIRISH (ADMIN)
# =====================================================
@router.message(Command("delad"))
async def delete_ad_cmd(message: Message, session: AsyncSession):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("⚠️ Format: <code>/delad ELON_ID</code>", parse_mode="HTML")
        return

    ad_id = parts[1]
    result = await session.execute(select(Ad).where(Ad.id.startswith(ad_id)))
    ad = result.scalar_one_or_none()

    if not ad:
        await message.answer("❌ E'lon topilmadi.")
        return

    await session.delete(ad)
    await session.commit()
    await message.answer(f"🗑 E'lon o'chirildi: {ad.title[:50]}")


@router.message(Command("delplace"))
async def delete_place_cmd(message: Message, session: AsyncSession):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("⚠️ Format: <code>/delplace DO'KON_ID</code>", parse_mode="HTML")
        return

    place_id = parts[1]
    result = await session.execute(select(Place).where(Place.id.startswith(place_id)))
    place = result.scalar_one_or_none()

    if not place:
        await message.answer("❌ Do'kon topilmadi.")
        return

    await session.delete(place)
    await session.commit()
    await message.answer(f"🗑 Do'kon o'chirildi: {place.name}")


# =====================================================
# XABARNOMA (BROADCAST)
# =====================================================
@router.callback_query(F.data == "admin_broadcast_start")
async def start_broadcast(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return

    await callback.message.answer(
        "📢 <b>Xabarnoma yuborish</b>\n\n"
        "Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni yuboring.\n"
        "Bekor qilish uchun /cancel yozing.",
        parse_mode="HTML"
    )
    await state.set_state(AdminBroadcast.message)
    await callback.answer()


@router.message(AdminBroadcast.message)
async def preview_broadcast(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Xabarnoma bekor qilindi.", reply_markup=admin_panel_keyboard())
        return

    await state.update_data(msg_id=message.message_id)

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Nusxa", callback_data="broadcast_confirm_copy")
    kb.button(text="♻️ Forward", callback_data="broadcast_confirm_forward")
    kb.button(text="❌ Bekor", callback_data="broadcast_cancel")
    kb.adjust(2, 1)

    await message.copy_to(message.chat.id)
    await message.answer(
        "Tepadagi xabar barchaga yuboriladi. Usulni tanlang:",
        reply_markup=kb.as_markup()
    )
    await state.set_state(AdminBroadcast.confirm)


@router.callback_query(AdminBroadcast.confirm, F.data == "broadcast_cancel")
async def cancel_broadcast(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Xabarnoma bekor qilindi.")
    await callback.answer()


@router.callback_query(
    AdminBroadcast.confirm,
    F.data.in_(["broadcast_confirm_copy", "broadcast_confirm_forward"])
)
async def send_broadcast(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    if not is_admin(callback.from_user.id):
        return

    mode = "copy" if callback.data == "broadcast_confirm_copy" else "forward"
    data = await state.get_data()
    msg_id = data.get("msg_id")

    result = await session.execute(select(User.telegram_id).where(User.is_blocked == False))
    users = result.scalars().all()

    await callback.message.edit_text(
        f"🚀 <b>Xabarnoma {len(users)} ta foydalanuvchiga yuborilmoqda...</b>\n"
        "Fonda bajariladi. Yakunida hisobot keladi.",
        parse_mode="HTML"
    )

    asyncio.create_task(
        _background_broadcast(
            bot=callback.bot,
            users=users,
            from_chat_id=callback.message.chat.id,
            msg_id=msg_id,
            admin_id=callback.from_user.id,
            mode=mode
        )
    )

    await state.clear()
    await callback.answer()


async def _background_broadcast(bot, users, from_chat_id, msg_id, admin_id, mode="copy"):
    sent, failed = 0, 0

    for user_id in users:
        try:
            if mode == "copy":
                await bot.copy_message(chat_id=user_id, from_chat_id=from_chat_id, message_id=msg_id)
            else:
                await bot.forward_message(chat_id=user_id, from_chat_id=from_chat_id, message_id=msg_id)
            sent += 1
            await asyncio.sleep(0.05)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            try:
                if mode == "copy":
                    await bot.copy_message(chat_id=user_id, from_chat_id=from_chat_id, message_id=msg_id)
                else:
                    await bot.forward_message(chat_id=user_id, from_chat_id=from_chat_id, message_id=msg_id)
                sent += 1
            except Exception:
                failed += 1
        except Exception:
            failed += 1

    try:
        await bot.send_message(
            chat_id=admin_id,
            text=(
                f"✅ <b>Xabarnoma yakunlandi!</b>\n\n"
                f"✅ Yetkazildi: <b>{sent} ta</b>\n"
                f"❌ Xatolik: <b>{failed} ta</b>"
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Hisobot yuborishda xato: {e}")