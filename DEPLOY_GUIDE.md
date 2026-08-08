# Saroyliklar: Render + Supabase

Loyiha bitta bepul Render Web Service ichida FastAPI va Telegram webhook sifatida ishlaydi. PostgreSQL ma'lumotlari ham, rasm va videolar ham bitta Supabase project ichida saqlanadi. Render lokal diskiga foydalanuvchi fayllari yozilmaydi.

## 1. Telegram bot

1. Telegram'da `@BotFather` orqali bot yarating va tokenni oling.
2. `ADMIN_IDS` uchun o'z Telegram raqamli ID'ingizni kiriting. Bir nechta admin vergul bilan yoziladi: `123456789,987654321`.
3. Oldingi token Git tarixiga tushgan bo'lsa, BotFather orqali uni darhol yangilang.

## 2. Supabase project va baza

1. [Supabase Dashboard](https://supabase.com/dashboard) da bepul project yarating va database parolini xavfsiz joyda saqlang.
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

## 3. Supabase Storage

1. Supabase project ichida `Storage` bo'limini oching.
2. `New bucket` tugmasini bosing.
3. Bucket nomini aynan `saroyliklar-media` deb yozing.
4. `Public bucket` parametrini yoqing. E'lon rasmlari va videolari WebApp hamda Telegram kanalida ochilishi uchun bucket public bo'lishi kerak.
5. File size limit'ni `20 MB` qilib belgilang.
6. Ruxsat etilgan MIME turlariga quyidagilarni kiriting:

```text
image/jpeg,image/png,image/webp,image/gif,video/mp4,video/webm,video/quicktime
```

Keyin `Project Settings -> API Keys` bo'limidan quyidagilarni oling:

- `Project URL` -> `SUPABASE_URL`
- Yangi formatdagi `Secret key` -> `SUPABASE_SECRET_KEY`
- Agar Secret key ko'rinmasa, eski `service_role` kalitini `SUPABASE_SERVICE_ROLE_KEY` nomi bilan ishlatish ham mumkin.

Muhim: Secret yoki service-role kalitini HTML, JavaScript yoki GitHub'ga joylamang. U faqat Render backend Environment ichida turishi kerak. Public bucket fayllarni o'qishga ochiq qiladi, lekin yuklash va o'chirish faqat backend maxfiy kaliti orqali bajariladi.

Supabase Free rejada jami 1 GB Storage va bitta fayl uchun ko'pi bilan 50 MB limit mavjud. Loyiha xavfsiz standart sifatida 20 MB limitdan foydalanadi.

## 4. GitHub'ga joylash

`.env` GitHub'ga yuborilmaydi. Agar u oldin Git'ga qo'shilgan bo'lsa:

```powershell
git rm --cached .env
git add .
git commit -m "Use Supabase Storage on Render"
git push origin main
```

`.env`, bot tokeni, Supabase database paroli, Secret/service-role key yoki admin parolini commit qilmang. Oldingi repoda haqiqiy kalitlar saqlangan bo'lsa, ularning barchasini yangilang.

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
| `DATABASE_URL` | Supabase Session pooler satri |
| `SUPABASE_URL` | `https://PROJECT_REF.supabase.co` |
| `SUPABASE_SECRET_KEY` | Supabase Secret key yoki service-role key |
| `SUPABASE_STORAGE_BUCKET` | `saroyliklar-media` |
| `GEMINI_API_KEY` | Ixtiyoriy |

`ADMIN_SECRET_KEY` Render tomonidan avtomatik yaratiladi. `WEBHOOK_SECRET` uchun Telegram qabul qiladigan URL-safe qiymat yarating:

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

`/health` javobida `storage` va `database` qiymatlari `supabase` bo'lishi kerak.

## 6. Bot va WebApp tekshiruvi

1. Botga `/start` yuboring va telefon raqamingizni ulashing.
2. `Xarita va E'lonlar` tugmasini oching.
3. WebApp'dan rasmli va videoli test e'lon yuboring.
4. Supabase `Storage -> saroyliklar-media` ichida fayl paydo bo'lganini tekshiring.
5. Admin panel yoki Telegram admin tugmasi orqali e'lonni tasdiqlang.
6. Xarita markerini, detail oynasini, qo'ng'iroq tugmasini va e'lonni o'chirishni tekshiring.
7. E'lon o'chirilganda uning Storage fayli ham yo'qolganini tekshiring.

## 7. Eski Google Drive fayllari

Yangi yuklamalar faqat Supabase Storage'ga tushadi. Google Drive'da oldindan mavjud bo'lgan fayllar avtomatik ko'chirilmaydi. Eski bazadagi `public_url` ishlashda davom etishi mumkin, lekin Google Drive fayllarini o'chirish endi bot tomonidan boshqarilmaydi. Kerakli eski rasmlarni qo'lda Supabase bucket'ga yuklash yoki e'lonlarni qayta yaratish mumkin.

Render Environment'dan eski quyidagi qiymatlarni o'chirish mumkin:

```text
GOOGLE_DRIVE_CLIENT_ID
GOOGLE_DRIVE_CLIENT_SECRET
GOOGLE_DRIVE_REFRESH_TOKEN
GOOGLE_DRIVE_FOLDER_ID
GOOGLE_DRIVE_PUBLIC
```

## 8. Bepul rejalar cheklovi

Render Free web service 15 daqiqa kiruvchi trafik bo'lmasa uxlaydi. Keyingi Telegram xabari yoki WebApp so'rovida uyg'onish biroz vaqt olishi mumkin. Supabase Free Storage 1 GB bilan cheklanganligi sababli, videolar uchun hajm nazoratini saqlang va keraksiz e'lonlarni admin paneldan o'chirib boring.

## Lokal ishga tushirish

1. `.env.example` dan `.env` yarating va qiymatlarni kiriting.
2. Supabase database URL, project URL va Secret key'ni kiriting.
3. Serverni boshlang:

```powershell
python -m pip install -r requirements.txt
uvicorn bot:app --host 0.0.0.0 --port 8000 --reload
```

Telegram webhook lokal `http://localhost` ga kelmaydi. Botning real webhook sinovi uchun HTTPS tunnel yoki Render URL'i kerak. WebApp'ni Telegram tashqarisida faqat lokal tekshirish uchun `.env` da `DEV_TELEGRAM_ID` ni o'z ID'ingizga qo'ying va `/webapp?dev_tg_id=ID` ni oching; production'da bu qiymat har doim `0` bo'lishi shart.
