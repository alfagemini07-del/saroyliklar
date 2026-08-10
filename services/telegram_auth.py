import hashlib
import hmac
import json
import time
from collections import deque
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException, Query

from config import BOT_TOKEN, DEBUG, DEV_TELEGRAM_ID


MAX_INIT_DATA_AGE_SECONDS = 24 * 60 * 60
MAX_INIT_DATA_LENGTH = 16 * 1024
API_RATE_WINDOW_SECONDS = 60
API_RATE_LIMIT = 120
_request_times: dict[int, deque[float]] = {}


def _enforce_rate_limit(user_id: int) -> None:
    now = time.monotonic()
    requests = _request_times.setdefault(user_id, deque())
    cutoff = now - API_RATE_WINDOW_SECONDS
    while requests and requests[0] <= cutoff:
        requests.popleft()
    if len(requests) >= API_RATE_LIMIT:
        retry_after = max(1, int(API_RATE_WINDOW_SECONDS - (now - requests[0])))
        raise HTTPException(
            status_code=429,
            detail="Juda ko'p so'rov yuborildi. Birozdan keyin qayta urinib ko'ring",
            headers={"Retry-After": str(retry_after)},
        )
    requests.append(now)
    if len(_request_times) > 10_000:
        stale = [key for key, values in _request_times.items() if not values or values[-1] <= cutoff]
        for key in stale:
            _request_times.pop(key, None)
        while len(_request_times) > 10_000:
            _request_times.pop(next(iter(_request_times)))


def verify_init_data(init_data: str) -> dict:
    if not init_data:
        raise HTTPException(status_code=401, detail="Telegram orqali oching")
    if len(init_data) > MAX_INIT_DATA_LENGTH:
        raise HTTPException(status_code=401, detail="Telegram sessiyasi formati noto'g'ri")

    values = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = values.pop("hash", "")
    if not received_hash:
        raise HTTPException(status_code=401, detail="Telegram imzosi topilmadi")

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(values.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated_hash, received_hash):
        raise HTTPException(status_code=401, detail="Telegram imzosi noto'g'ri")

    try:
        auth_date = int(values.get("auth_date", "0") or 0)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Telegram sessiyasi vaqti noto'g'ri") from exc
    now = time.time()
    if not auth_date or auth_date > now + 60 or now - auth_date > MAX_INIT_DATA_AGE_SECONDS:
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
        user = verify_init_data(init_data)
        _enforce_rate_limit(int(user["id"]))
        return user
    if DEBUG and DEV_TELEGRAM_ID and dev_tg_id == DEV_TELEGRAM_ID:
        _enforce_rate_limit(DEV_TELEGRAM_ID)
        return {"id": DEV_TELEGRAM_ID, "first_name": "Development user"}
    raise HTTPException(status_code=401, detail="Web Appni Telegram ichidan oching")
