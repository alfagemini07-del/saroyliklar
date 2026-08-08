from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardRemove, WebAppInfo
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from config import WEBAPP_URL, CATEGORIES, REGIONS, CURRENCIES, WEBHOOK_URL


# =====================================================
# ASOSIY MENYU
# =====================================================
def main_menu():
    separator = "&" if "?" in WEBAPP_URL else "?"
    safe_webapp_url = f"{WEBAPP_URL}{separator}v=3"
    
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(
                text="🗺️ Xarita va E'lonlar",
                web_app=WebAppInfo(url=safe_webapp_url)
            )],
            [KeyboardButton(text="📝 E'lon joylash")],
            [KeyboardButton(text="🏪 Do'kon ochish"), KeyboardButton(text="👤 Profilim")],
            [KeyboardButton(text="📋 Mening e'lonlarim"), KeyboardButton(text="👨‍💻 Aloqa")],
        ],
        resize_keyboard=True
    )
    return kb


# =====================================================
# TELEFON RAQAM KLAVIATURASI
# =====================================================
def phone_keyboard():
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Raqamimni ulashish", request_contact=True)],
            [KeyboardButton(text="❌ Bekor qilish")],
        ],
        resize_keyboard=True
    )
    return kb


# =====================================================
# BEKOR QILISH / O'TKAZIB YUBORISH
# =====================================================
def remove_keyboard():
    return ReplyKeyboardRemove()


def cancel_keyboard():
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Bekor qilish")]],
        resize_keyboard=True
    )
    return kb


def skip_cancel_keyboard():
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⏭ O'tkazib yuborish")],
            [KeyboardButton(text="❌ Bekor qilish")],
        ],
        resize_keyboard=True
    )
    return kb


# =====================================================
# LOKATSIYA KLAVIATURASI
# =====================================================
def location_keyboard():
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Lokatsiyamni ulashish", request_location=True)],
            [KeyboardButton(text="⏭ O'tkazib yuborish")],
            [KeyboardButton(text="❌ Bekor qilish")],
        ],
        resize_keyboard=True
    )
    return kb


# =====================================================
# KATEGORIYALAR INLINE KLAVIATURASI
# =====================================================
def categories_keyboard(selected: str = None, prefix: str = "cat"):
    kb = InlineKeyboardBuilder()
    for key, cat in CATEGORIES.items():
        mark = "✅ " if selected == key else ""
        kb.button(
            text=f"{mark}{cat['icon']} {cat['name']}",
            callback_data=f"{prefix}_{key}"
        )
    kb.adjust(2)
    return kb.as_markup()


# =====================================================
# VALYUTA TANLASH
# =====================================================
def currency_keyboard(prefix: str = "currency"):
    kb = InlineKeyboardBuilder()
    kb.button(text="💵 USD (Dollar)", callback_data=f"{prefix}_USD")
    kb.button(text="🏦 UZS (So'm)",   callback_data=f"{prefix}_UZS")
    kb.adjust(2)
    return kb.as_markup()


# =====================================================
# HA/YO'Q KLAVIATURASI
# =====================================================
def yes_no_keyboard(yes_data: str, no_data: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Ha", callback_data=yes_data)
    kb.button(text="❌ Yo'q", callback_data=no_data)
    kb.adjust(2)
    return kb.as_markup()


# =====================================================
# E'LON TASDIQLASH (FOYDALANUVCHI UCHUN)
# =====================================================
def ad_confirm_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Joylash",      callback_data="ad_confirm_yes")
    kb.button(text="✏️ Qaytadan",    callback_data="ad_confirm_edit")
    kb.button(text="❌ Bekor qilish", callback_data="ad_confirm_no")
    kb.adjust(2, 1)
    return kb.as_markup()


# =====================================================
# ADMIN UCHUN E'LON TASDIQLASH
# =====================================================
def admin_ad_approve_keyboard(ad_id: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Tasdiqlash",  callback_data=f"approve_ad_{ad_id}")
    kb.button(text="❌ Rad etish",   callback_data=f"reject_ad_{ad_id}")
    kb.adjust(2)
    return kb.as_markup()


# =====================================================
# ADMIN UCHUN DO'KON TASDIQLASH
# =====================================================
def admin_place_approve_keyboard(place_id: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Faollashtirish", callback_data=f"approve_place_{place_id}")
    kb.button(text="❌ Rad etish",      callback_data=f"reject_place_{place_id}")
    kb.button(text="⭐ Verifikatsiya",  callback_data=f"verify_place_{place_id}")
    kb.adjust(2, 1)
    return kb.as_markup()


# =====================================================
# MENING E'LONLARIM — AMALLAR
# =====================================================
def my_ad_actions_keyboard(ad_id: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="🗑 O'chirish",  callback_data=f"delete_ad_{ad_id}")
    kb.button(text="🔄 Yangilash", callback_data=f"renew_ad_{ad_id}")
    kb.adjust(2)
    return kb.as_markup()


# =====================================================
# DO'KON PROFIL AMALLAR
# =====================================================
def place_actions_keyboard(place_id: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="🖼 Rasm qo'shish",  callback_data=f"add_photo_{place_id}")
    kb.button(text="✏️ Tahrirlash",     callback_data=f"edit_place_{place_id}")
    kb.button(text="🗑 O'chirish",       callback_data=f"delete_place_{place_id}")
    kb.adjust(2, 1)
    return kb.as_markup()


# =====================================================
# ADMIN BILAN ALOQA
# =====================================================
def admin_contact_link_keyboard(link: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="👨‍💻 Adminga yozish", url=link)
    return kb.as_markup()


# =====================================================
# ADMIN PANEL
# =====================================================
def admin_panel_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Statistika",         callback_data="admin_stats")
    kb.button(text="📢 Xabarnoma",          callback_data="admin_broadcast_start")
    kb.button(text="⚙️ Qo'llanma",         callback_data="admin_help")
    kb.adjust(1)
    return kb.as_markup()
