# Saroyliklar: Render + Supabase + Google Drive

Ushbu loyiha bitta bepul Render Web Service ichida FastAPI va Telegram webhook sifatida ishlaydi. PostgreSQL ma'lumotlari Supabase'da, rasm va videolar Google Drive'da saqlanadi.

## 1. Telegram bot

1. Telegram'da `@BotFather` orqali bot yarating va tokenni oling.
2. `ADMIN_IDS` uchun o'z Telegram raqamli ID'ingizni kiriting. Bir nechta admin vergul bilan yoziladi: `123456789,987654321`.
3. Oldingi token Git tarixiga tushgan bo'lsa, BotFather orqali uni darhol yangilang.

## 2. Supabase bazasi

1. [Supabase](https://supabase.com/dashboard) da bepul project yarating va database parolini xavfsiz joyda saqlang.
2. Project oynasida `Connect` tugmasini bosing.
3. `Session pooler` ulanishini tanlang. Render IPv4 muhitida port `5432` dagi session pooler ishlatiladi.
4. Ulanish satrining boshini `postgresql+asyncpg://` ga almashtiring:

```text
postgresql+asyncpg://postgres.PROJECT_REF:PASSWORD@aws-0-REGION.pooler.supabase.com:5432/postgres
```

5. Parolda `@`, `:`, `/`, `#` kabi belgilar bo'lsa URL-formatga kodlang:

```powershell
python -c "from urllib.parse import quote_plus; print(quote_plus('SIZNING_PAROLINGIZ'))"
```

Jadvallar birinchi startda avtomatik yaratiladi. Eski versiyadagi baza ishlatilsa, kerakli media ustunlari idempotent migratsiya bilan qo'shiladi.

## 3. Google Drive OAuth

Shaxsiy bepul Google Drive uchun service account ishlatmang: service account fayl egasi bo'la olmaydi. Loyiha OAuth refresh token bilan sizning Drive hisobingiz nomidan ishlaydi.

1. [Google Cloud Console](https://console.cloud.google.com/) da project yarating.
2. `APIs & Services -> Library` dan `Google Drive API` ni yoqing.
3. `Google Auth Platform -> Audience` da `External` ni tanlang va Google hisobingizni test user sifatida qo'shing.
4. `Clients -> Create client -> Desktop app` orqali OAuth client yarating.
5. Client ID va Client Secret'ni lokal `.env` faylga kiriting:

```env
GOOGLE_DRIVE_CLIENT_ID=...
GOOGLE_DRIVE_CLIENT_SECRET=...
```

6. Lokal kompyuterda kutubxonalarni o'rnating va yordamchi skriptni ishga tushiring:

```powershell
python -m pip install -r requirements.txt
python scripts/google_drive_auth.py
```

7. Brauzerda aynan media saqlanadigan Google hisobini tanlang. Skript `Saroyliklar Media` papkasini yaratadi va quyidagi ikki qiymatni chiqaradi:

```env
GOOGLE_DRIVE_REFRESH_TOKEN=...
GOOGLE_DRIVE_FOLDER_ID=...
```

Muhim: Google OAuth ilovasi `Testing` holatida bo'lsa Drive scope bilan olingan refresh token 7 kunda tugaydi. Sinovdan keyin OAuth ilovasini `In production` holatiga o'tkazing va tokenni skript orqali qayta oling. Bu OAuth faqat bitta, o'zingizning Drive hisobingiz uchun ishlatiladi.

## 4. GitHub'ga joylash

`.env` GitHub'ga yuborilmaydi. Agar u oldin Git'ga qo'shilgan bo'lsa:

```powershell
git rm --cached .env
git add .
git commit -m "Prepare Saroyliklar for Render"
git push origin main
```

`.env`, bot tokeni, Supabase paroli, Google refresh tokeni yoki admin parolini commit qilmang. Oldingi repoda haqiqiy kalitlar saqlangan bo'lsa, ularning barchasini yangilang.

## 5. Render Blueprint

1. [Render Dashboard](https://dashboard.render.com/) da `New -> Blueprint` ni tanlang.
2. GitHub repository'ni ulang. Render ildizdagi `render.yaml` faylini topadi.
3. `sync: false` deb ko'rsatilgan qiymatlarni kiriting:

| Kalit | Qiymat |
|---|---|
| `BOT_TOKEN` | BotFather tokeni |
| `ADMIN_IDS` | Telegram admin ID'lari |
| `ADMIN_USERNAME` | Web admin login |
| `ADMIN_PASSWORD` | Kuchli web admin paroli |
| `WEBHOOK_SECRET` | Faqat harf, raqam, `_` va `-` dan iborat maxfiy satr |
| `PUBLIC_BASE_URL` | `https://SERVIS-NOMI.onrender.com` |
| `DATABASE_URL` | Supabase session pooler satri |
| `GOOGLE_DRIVE_CLIENT_ID` | Google OAuth client ID |
| `GOOGLE_DRIVE_CLIENT_SECRET` | Google OAuth client secret |
| `GOOGLE_DRIVE_REFRESH_TOKEN` | Skript chiqargan token |
| `GOOGLE_DRIVE_FOLDER_ID` | Skript yaratgan papka ID'si |
| `GEMINI_API_KEY` | Ixtiyoriy |

`ADMIN_SECRET_KEY` Render tomonidan avtomatik yaratiladi. `WEBHOOK_SECRET` uchun quyidagi buyruq bilan Telegram qabul qiladigan URL-safe qiymat yarating:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

4. Service yaratilgach uning aniq URL'ini tekshiring. Agar slug kutilganidan farq qilsa, `PUBLIC_BASE_URL` ni tuzating va `Manual Deploy -> Deploy latest commit` qiling.
5. Deploy logida `Database is ready` va `Telegram webhook is active` yozuvlari chiqishi kerak.

Tekshiruv URL'lari:

```text
https://SERVIS-NOMI.onrender.com/health
https://SERVIS-NOMI.onrender.com/webapp
https://SERVIS-NOMI.onrender.com/admin
```

## 6. Bot va Web App tekshiruvi

1. Botga `/start` yuboring va telefon raqamingizni ulashing.
2. `Xarita va E'lonlar` tugmasini oching.
3. Web App'dan rasmli va videoli test e'lon yuboring.
4. Google Drive'dagi `Saroyliklar Media` papkasida media paydo bo'lganini tekshiring.
5. Admin panel yoki Telegram admin tugmasi orqali e'lonni tasdiqlang.
6. Xarita markerini, detail oynasini, qo'ng'iroq tugmasini va e'lonni o'chirishni tekshiring.

## 7. Bepul Render cheklovi

Render Free web service 15 daqiqa kiruvchi trafik bo'lmasa uxlaydi. Keyingi Telegram xabari yoki Web App so'rovida uyg'onish taxminan bir daqiqa olishi mumkin. Lokal disk vaqtinchalik bo'lgani uchun loyiha runtime'da lokal media saqlamaydi. Yuqori trafik yoki doimiy tezkor javob kerak bo'lsa, Render'ning pullik instance'i kerak bo'ladi.

## Lokal ishga tushirish

1. `.env.example` dan `.env` yarating va qiymatlarni kiriting.
2. Lokal PostgreSQL yoki Supabase URL'ini ishlating.
3. Serverni boshlang:

```powershell
python -m pip install -r requirements.txt
uvicorn bot:app --host 0.0.0.0 --port 8000 --reload
```

Telegram webhook lokal `http://localhost` ga kelmaydi. Botning real webhook sinovi uchun HTTPS tunnel yoki Render URL'i kerak. Web App'ni Telegram tashqarisida faqat lokal tekshirish uchun `.env` da `DEV_TELEGRAM_ID` ni o'z ID'ingizga qo'ying va `/webapp?dev_tg_id=ID` ni oching; production'da bu qiymat har doim `0` bo'lishi shart.
