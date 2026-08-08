from aiogram.fsm.state import State, StatesGroup


# =====================================================
# RO'YXATDAN O'TISH
# =====================================================
class Register(StatesGroup):
    full_name = State()
    phone     = State()


# =====================================================
# E'LON YARATISH (Bot orqali)
# =====================================================
class CreateAd(StatesGroup):
    photos      = State()   # 1. Rasmlar yuklash (1-5 ta)
    description = State()   # 2. Tavsif yozish
    price       = State()   # 3. Narx kiritish
    location    = State()   # 4. Lokatsiya (haritadan yoki manzil)
    phone       = State()   # 5. Telefon raqam
    confirm     = State()   # 6. Tasdiqlash


# =====================================================
# DO'KON / PROFIL YARATISH (Bot orqali)
# =====================================================
class CreatePlace(StatesGroup):
    name        = State()   # 1. Do'kon nomi
    category    = State()   # 2. Kategoriya tanlash
    phone       = State()   # 3. Telefon raqam
    description = State()   # 4. Qisqa tavsif
    avatar      = State()   # 5. Profil rasmi (avatar)
    cover       = State()   # 6. Cover rasmi (banner)
    location    = State()   # 7. Lokatsiya
    hours       = State()   # 8. Ish vaqti
    social      = State()   # 9. Ijtimoiy tarmoqlar (telegram, instagram)
    confirm     = State()   # 10. Tasdiqlash


# =====================================================
# DO'KON RASMLAR QO'SHISH
# =====================================================
class AddPlacePhoto(StatesGroup):
    photo   = State()   # Rasm yuborish
    caption = State()   # Sarlavha / narx
    price   = State()   # Narx (ixtiyoriy)


# =====================================================
# PROFIL TAHRIRLASH
# =====================================================
class EditProfile(StatesGroup):
    full_name = State()
    phone     = State()
    region    = State()


# =====================================================
# ADMIN
# =====================================================
class AdminBroadcast(StatesGroup):
    message = State()
    confirm = State()


class AdminReject(StatesGroup):
    reason = State()   # Rad etish sababi