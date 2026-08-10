# Saroyliklar: Render + Supabase Postgres + Telegram Media

Loyiha bitta Render Web Service ichida FastAPI, Telegram webhook, Web App va admin panel sifatida ishlaydi. Ma'lumotlar Supabase Postgres'da, rasm va videolar esa private Telegram kanalda saqlanadi. Render diskiga foydalanuvchi fayllari yozilmaydi.

## 1. Telegram media kanalini tayyorlash

1. Telegram'da yangi **private channel** yarating. Masalan: `Saroyliklar Media Baza`.
2. Botni kanalga administrator qilib qo'shing.
3. Botga `Post messages` va `Delete messages` huquqlarini bering.
4. Private kanalning `-100...` bilan boshlanuvchi ID raqamini oling. Public kanal bo'lsa admin panelga `@username` ham kiritish mumkin.
5. Kanalni odamlar uchun ochmang. U faqat media arxiv bo'lib xizmat qiladi.

## 2. Supabase database

Supabase'dan **Session pooler** URL oling. Render'dagi `DATABASE_URL` qiymati quyidagi ko'rinishda bo'ladi:

```text
postgresql+asyncpg://postgres.PROJECT_REF:PASSWORD@aws-0-REGION.pooler.supabase.com:5432/postgres
```

Parolda `@`, `:`, `/`, `#`, `%` kabi belgilar bo'lsa URL-encode qiling. Render uchun Session pooler porti `5432` ishlatiladi.

## 3. GitHub va Render

GitHub repository'ga kodni yuboring. `.env`, bot tokeni, database paroli va admin parolini commit qilmang.

Render'da `New -> Blueprint` orqali repository'ni tanlang. `render.yaml` build va start buyruqlarini o'zi oladi.

Render `Environment` bo'limiga quyidagilarni kiriting:

| Key | Value |
| --- | --- |
| `BOT_TOKEN` | BotFather bergan token |
| `ADMIN_IDS` | Telegram ID'lar, vergul bilan |
| `ADMIN_USERNAME` | Admin panel login |
| `ADMIN_PASSWORD` | Kuchli admin paroli |
| `ADMIN_SECRET_KEY` | Render yaratadi yoki uzun tasodifiy qiymat |
| `WEBHOOK_SECRET` | Uzun tasodifiy qiymat |
| `DATABASE_URL` | Supabase Session pooler URL |
| `ENVIRONMENT` | `production` |
| `MAX_UPLOAD_MB` | `10` |
| `MEDIA_CACHE_MB` | `64` |

`SUPABASE_URL`, `SUPABASE_SECRET_KEY` va `SUPABASE_STORAGE_BUCKET` media uchun endi kerak emas. Supabase faqat PostgreSQL database sifatida qoladi.

## 4. Birinchi deploy va kanalni ulash

1. Render deploy tugagach `https://saroyliklar.onrender.com/health` sahifasini oching.
2. Javobda `storage: telegram-channel` bo'lishi kerak.
3. `https://saroyliklar.onrender.com/admin` manziliga kiring.
4. `Sozlamalar -> Media saqlash kanali ID` maydoniga `-100...` ID yoki public `@username` kiriting.
5. `Saqlash` tugmasini bosing. Panel kanal va bot huquqlarini tekshiradi va kanal nomini ko'rsatadi.
6. Botdagi Web App orqali sinov mahsuloti yarating. Kanalga fayl-xabar tushishi va mahsulot rasmi Web App'da ochilishini tekshiring.

## 5. Ishlash tartibi

- Har bir rasm yoki video ko'pi bilan 10 MB.
- JPG, PNG, WEBP, GIF, MP4, WEBM va MOV qabul qilinadi.
- Kanalga yuborilgan Telegram `file_id` va `message_id` Supabase database'dagi `media_objects` jadvalida saqlanadi.
- Web App rasmlarni imzolangan `/media/{id}` proksi orqali oladi. Bot tokeni va kanal ID tashqariga chiqmaydi.
- Mahsulot o'chirilganda bot kanal xabarini ham o'chirishga urinadi.
- Eski Supabase rasmlarining bazada saqlangan `public_url` manzillari ishlashda davom etadi; yangi fayllar Telegram kanaliga tushadi.

## 6. Muhim cheklovlar

Telegram kanal media arxiv sifatida qulay va bepul, lekin klassik CDN emas. Bir vaqtda juda ko'p yangi rasm so'ralganda tezlik Telegram va Render Free resurslariga bog'liq. Server 64 MB gacha tezkor kesh, brauzer esa 24 soatlik kesh ishlatadi.

Render Free servis trafik bo'lmasa uxlaydi; birinchi ochilish sekinroq bo'lishi mumkin. Media kanalini yoki undagi xabarlarni qo'lda o'chirmang. Bot tokenini yangilasangiz, Render'dagi `BOT_TOKEN`ni ham yangilang va redeploy qiling.
