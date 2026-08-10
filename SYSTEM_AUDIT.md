# Saroyliklar tizimi auditi

Sana: 2026-08-10

## 1. Tizim qanday ishlaydi

1. Foydalanuvchi Telegram botda `/start` buyrug'ini yuboradi.
2. Bot ism va telefonni oladi, foydalanuvchini Supabase Postgres bazasida saqlaydi.
3. Telegram menu yoki inline tugma Mini App manzilini ochadi.
4. Mini App har bir API so'roviga Telegram `initData` qiymatini yuboradi.
5. FastAPI `initData` HMAC imzosini va `auth_date` vaqtini tekshiradi.
6. Do'konlar, mahsulotlar va koordinatalar Supabase Postgres bazasida saqlanadi.
7. Rasm va videolar private Telegram media kanaliga arxivlanadi.
8. Web App rasmni imzolangan `/media/{id}?sig=...` proksi manzili orqali oladi.
9. Admin panel cookie asosidagi HMAC sessiya orqali himoyalanadi.
10. Telegram update'lari faqat secret-token bilan himoyalangan webhook orqali qabul qilinadi.

## 2. Hozirgi kuchli tomonlar

- Telegram foydalanuvchisi frontend qiymatiga ishonib emas, serverdagi HMAC tekshiruvi bilan aniqlanadi.
- `auth_date` eskirishi va kelajakdagi noto'g'ri vaqtlar rad etiladi.
- Production rejimida `DEV_TELEGRAM_ID` ishlashi bloklangan.
- Marketplace API Telegram autentifikatsiyasiz ochilmaydi.
- Foydalanuvchi faqat o'z do'koni va mahsulotlarini o'zgartira oladi.
- Bloklangan foydalanuvchi Web App operatsiyalaridan cheklanadi.
- Media fayl kengaytmasi emas, haqiqiy bayt sarlavhasi tekshiriladi.
- Media URL HMAC imzoga ega va media proksi `nosniff`, ETag, Range hamda cache headerlarini qo'llaydi.
- Private media kanalda botning admin va post huquqlari tekshiriladi.
- Webhook alohida secret-token bilan himoyalangan.
- Admin paroli `compare_digest` orqali tekshiriladi, cookie `HttpOnly`, productionda `Secure`.
- Admin login urinishlari 15 daqiqada 5 marta bilan cheklangan.
- Web App API bir foydalanuvchi uchun 120 so'rov/minut bilan cheklangan.
- Xarita so'rovi faqat ko'rinayotgan hududni va 15% zaxira chegarani oladi.
- Statik CSS/JS bir hafta keshlanadi; bu Render yukini kamaytiradi.

## 3. Kritik xavflar va choralar

### P0 - darhol

1. Oldin chat, rasm yoki logda ko'ringan barcha maxfiy kalitlarni almashtirish:
   `BOT_TOKEN`, `DATABASE_URL` paroli, AI kalitlari, `ADMIN_PASSWORD`,
   `ADMIN_SECRET_KEY`, `WEBHOOK_SECRET`.
2. Admin parolini kamida 16-20 belgili, boshqa joyda ishlatilmagan parol qilish.
3. Supabase bazasidan muntazam SQL eksport olish. Free tarif avtomatik backup bermaydi.
4. Private media kanal egasi sifatida kamida ikki ishonchli administrator qoldirish.

### P1 - keyingi reliz

1. Admin amallari uchun audit log: kim, qachon, nimani tasdiqladi yoki o'chirdi.
2. Tasdiqlangan do'kon nomi, kategoriyasi yoki koordinatasi o'zgarsa qayta moderatsiya.
3. Shikoyat yuborish va bloklash sababi: foydalanuvchi, do'kon va mahsulot darajasida.
4. Media uchun thumbnail yaratish. Katalogda 10 MB original emas, 50-150 KB rasm ishlatilishi kerak.
5. Broadcast va rejalashtirilgan vazifalarni process ichidagi `asyncio.create_task` emas,
   doimiy queue orqali bajarish.
6. Sentry yoki boshqa error monitoring, uptime tekshiruvi va Telegram admin ogohlantirishi.
7. Database migration uchun Alembic. Hozirgi `ALTER TABLE IF NOT EXISTS` usuli kichik loyiha uchun yetarli,
   lekin murakkab schema o'zgarishlarida xavfli.

### P2 - o'sish bosqichi

1. Admin uchun Telegram tasdiqlash kodi yoki ikki bosqichli kirish.
2. Media imzosiga amal qilish muddati va kerak bo'lganda URL yangilash.
3. Foydalanuvchi sessiyasi va xavfsizlik hodisalarini alohida jadvalda kuzatish.
4. Bot va Web App uchun avtomatik unit, API va brauzer testlari.
5. Maxfiy kalitlarni Render Environment Group yoki secret manager orqali boshqarish.

## 4. Render, Supabase va media sig'imi

- Render Free 15 daqiqa kiruvchi trafik bo'lmasa servisni uxlatadi. Birinchi so'rovning
  uyg'onishi taxminan bir daqiqagacha cho'zilishi mumkin.
- Render Free istalgan vaqtda qayta ishga tushishi mumkin. `MemoryStorage` ichidagi FSM holatlari
  va process ichidagi broadcast vazifalari yo'qoladi.
- Supabase Free hozir 500 MB database va 5 GB egress bilan cheklangan.
- Rasmni Telegram kanalida saqlash database hajmini tejaydi, lekin har bir cache miss paytida
  Render Telegramdan fayl olib foydalanuvchiga uzatadi.
- 64 MB RAM media cache mashhur rasmlar uchun foydali, lekin yuzlab turli original rasm bir paytda
  ochilsa Render xotirasi va tashqi trafik asosiy to'siq bo'ladi.
- Eng muhim optimizatsiya: original + thumbnail juftligi, lazy loading va bir sahifada 20 tadan ko'p
  mahsulot yuklamaslik.

## 5. Xarita holati

Amalga oshirildi:

- Boshlang'ich nuqta: `40.167796262859696, 67.80262130723996`, zoom 16.
- Sun'iy yo'ldosh asosiy qatlam.
- Yo'llar, ko'chalar, hudud va joy nomlari uchun Esri reference qatlamlari.
- Oddiy OpenStreetMap ko'cha xaritasiga o'tish boshqaruvi.
- Kategoriya rangidagi kategoriya ikonkalari.
- Marker ustida do'kon nomi va kategoriya tooltip'i.
- Marker bosilganda do'kon kartasi va Google Maps yo'nalish tugmasi.
- Foydalanuvchi lokatsiyasi aniqlanganda aniqlik doirasi va ko'k nuqta.
- Xarita viewport bo'yicha server so'rovi va marker clustering.
- Do'kon joyini tanlash xaritasida ham yo'l va joy nomlari.

Keyingi xarita funksiyalari:

1. Masofa bo'yicha saralash va `Menga yaqin` rejimi.
2. `Hozir ochiq` filtri.
3. Yetkazib berish hududi poligoni.
4. Bir koordinataga juda ko'p do'kon qo'yilsa admin ogohlantirishi.
5. Mahalla chegarasi va ko'cha kesimida do'kon soni heatmap'i.

## 6. Foydalanuvchi uchun qulay funksiyalar

### Eng foydali birinchi bosqich

1. Sevimli mahsulot va do'konlar.
2. Do'konga obuna bo'lish va yangi mahsulot chiqqanda Telegram xabari.
3. Narx, masofa, yangilik va mashhurlik bo'yicha saralash.
4. `Hozir ochiq`, `Yetkazib beradi`, `Tasdiqlangan` filtrlari.
5. Mahsulotni Telegram guruh yoki shaxsiy chatga ulashish.
6. Do'kon egasiga tayyor savol yuborish: narxi, mavjudligi, yetkazib berish.
7. Ko'rilgan mahsulotlar tarixi.
8. Noto'g'ri narx, rasm yoki manzil haqida shikoyat.

### Keyingi bosqich

1. Savatcha va buyurtma so'rovi, dastlab onlayn to'lovsiz.
2. Buyurtma holati: yangi, qabul qilindi, tayyor, yetkazildi, bekor qilindi.
3. Faqat haqiqiy buyurtmadan keyingi baho va sharh.
4. Mahsulot variantlari: o'lcham, rang, vazn.
5. O'zbek va rus tillari.
6. Katta shrift va accessibility rejimi.

## 7. Sotuvchi uchun funksiyalar

1. Mahsulotni nusxalash va rasmlar tartibini almashtirish.
2. Omborda bor/yo'q tugmasi va qoldiq soni.
3. Aksiya narxi va aksiya tugash vaqti.
4. Ish vaqti bo'yicha avtomatik `ochiq/yopiq` holati.
5. Ko'rishlar, aloqa bosishlari va yo'nalish ochish statistikasi.
6. Telegram kanal postini mahsulot qo'shilganda preview qilish.
7. QR kod orqali do'kon profilini ulashish.
8. Sotuvchi xodimlari uchun cheklangan rollar.
9. Excel/CSV orqali ommaviy mahsulot importi.

## 8. Admin uchun funksiyalar

1. Moderatsiya navbati va oldingi/yangi qiymatlar farqi.
2. Ommaviy tasdiqlash, rad etish va kategoriyani almashtirish.
3. Xarita orqali noto'g'ri va takroriy koordinatalarni topish.
4. Shikoyatlar markazi va bloklash sababi.
5. Do'kon verifikatsiyasi uchun hujjat yoki joyiga borib tekshirish statusi.
6. Rejalashtirilgan kanal postlari va post tarixi.
7. Media kanal, database, webhook va Render holati uchun health dashboard.
8. CSV eksport, database backup holati va tiklash qo'llanmasi.
9. Rollar: super-admin, moderator, kontent menejer, moliya.
10. Har bir muhim amal uchun audit log va Telegram ogohlantirish.

## 9. Rasmiy mahalla guruhi bilan integratsiya

1. `/yaqin` - foydalanuvchiga yaqin do'konlar.
2. `/qidir mahsulot` - guruh ichida inline natijalar.
3. Kunlik yoki haftalik yangi mahsulotlar dayjesti.
4. Tasdiqlangan do'kon yangiliklarini mavzu bo'yicha post qilish.
5. Guruhdagi reklama spamini aniqlash va tasdiqlangan marketplace havolasini taklif qilish.
6. Muhim mahalla e'lonlarini pin qilish va vaqti tugaganda avtomatik unpin.
7. So'rovnoma, tadbir eslatmasi va navbatchilik jadvali.
8. Guruhda faqat admin buyruqlarini qat'iy `ADMIN_IDS` va chat ID bilan cheklash.

## 10. Tavsiya etilgan rivojlantirish tartibi

1. Sirlarni almashtirish, backup va monitoring.
2. Thumbnail, sevimlilar, yaqinlik va `hozir ochiq` filtri.
3. Moderatsiya diff'i, shikoyatlar va audit log.
4. Sotuvchi statistikasi, aksiya va ombor holati.
5. Buyurtma so'rovi va keyin haqiqiy buyurtmaga bog'langan reyting.
6. Queue, Redis/FSM va paid hostingga o'tish mezonlari.

## Rasmiy manbalar

- Telegram Mini App initData: https://core.telegram.org/bots/webapps
- Render Free cheklovlari: https://render.com/docs/free
- Supabase tarif limitlari: https://supabase.com/pricing
- Leaflet layers control: https://leafletjs.com/reference.html#control-layers
- OpenStreetMap tile policy: https://operations.osmfoundation.org/policies/tiles/
- OWASP authentication: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
