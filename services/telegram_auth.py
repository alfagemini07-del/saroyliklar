import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException, Query

from config import BOT_TOKEN, DEBUG, DEV_TELEGRAM_ID


MAX_INIT_DATA_AGE_SECONDS = 24 * 60 * 60


def verify_init_data(init_data: str) -> dict:
    if not init_data:
        raise HTTPException(status_code=401, detail="Telegram orqali oching")

    values = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = values.pop("hash", "")
    if not received_hash:
        raise HTTPException(status_code=401, detail="Telegram imzosi topilmadi")

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(values.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated_hash, received_hash):
        raise HTTPException(status_code=401, detail="Telegram imzosi noto'g'ri")

    auth_date = int(values.get("auth_date", "0") or 0)
    if not auth_date or time.time() - auth_date > MAX_INIT_DATA_AGE_SECONDS:
        raise HTTPException(status_code=401, detail="Telegram sessiyasi eskirgan. Web Appni qayta oching")

    try:
        user = json.loads(values.get("user", "{}"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=401, detail="Telegram foydalanuvchisi aniqlanmadi") from exc
    if not user.get("id"):
        raise HTTPException(status_code=401, detail="Telegram foydalanuvchisi aniqlanmadi")
    return user


async def telegram_user(
    x_telegram_init_data: str = Header(default="", alias="X-Telegram-Init-Data"),
    authorization: str = Header(default=""),
    dev_tg_id: int | None = Query(default=None, include_in_schema=False),
) -> dict:
    auth_init_data = authorization[4:].strip() if authorization.lower().startswith("tma ") else ""
    init_data = x_telegram_init_data or auth_init_data
    if init_data:
        return verify_init_data(init_data)
    if DEBUG and DEV_TELEGRAM_ID and dev_tg_id == DEV_TELEGRAM_ID:
        return {"id": DEV_TELEGRAM_ID, "first_name": "Development user"}
    raise HTTPException(status_code=401, detail="Web Appni Telegram ichidan oching")
