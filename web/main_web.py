import base64
import hashlib
import hmac
import logging
import time

from aiogram import Bot, Dispatcher
from aiogram.types import Update
from fastapi import FastAPI, Form, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import (
    ADMIN_COOKIE_NAME,
    ADMIN_PASSWORD,
    ADMIN_SECRET_KEY,
    ADMIN_USERNAME,
    DEBUG,
    PUBLIC_BASE_URL,
    WEBHOOK_PATH,
    WEBHOOK_SECRET,
    _BASE_DIR,
)


logger = logging.getLogger(__name__)


def _admin_token() -> str:
    timestamp = str(int(time.time()))
    signature = hmac.new(ADMIN_SECRET_KEY.encode(), timestamp.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{timestamp}.{signature}".encode()).decode()


def _valid_admin_token(token: str | None) -> bool:
    if not token or not ADMIN_SECRET_KEY:
        return False
    try:
        payload = base64.urlsafe_b64decode(token.encode()).decode()
        timestamp, signature = payload.split(".", 1)
        if time.time() - int(timestamp) > 24 * 60 * 60:
            return False
        expected = hmac.new(ADMIN_SECRET_KEY.encode(), timestamp.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)
    except (ValueError, TypeError):
        return False


def init_web(bot: Bot, dp: Dispatcher) -> FastAPI:
    app = FastAPI(title="Saroyliklar", docs_url="/docs" if DEBUG else None, redoc_url=None)
    app.state.bot = bot
    app.state.dp = dp

    origins = ["https://t.me", "https://web.telegram.org", PUBLIC_BASE_URL]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "PUT"],
        allow_headers=["Content-Type", "Authorization", "X-Telegram-Init-Data"],
    )

    protected_api_prefixes = ("/api/admin", "/api/settings")

    @app.middleware("http")
    async def admin_auth(request: Request, call_next):
        path = request.url.path
        is_admin_page = path.startswith("/admin") and path != "/admin/login"
        is_admin_api = path.startswith(protected_api_prefixes)
        if (is_admin_page or is_admin_api) and not _valid_admin_token(request.cookies.get(ADMIN_COOKIE_NAME)):
            if is_admin_api:
                return JSONResponse({"detail": "Admin sessiyasi tugagan"}, status_code=401)
            return RedirectResponse("/admin/login", status_code=status.HTTP_303_SEE_OTHER)
        response = await call_next(request)
        if path == "/webapp" or path.startswith("/static/") or path.startswith("/admin"):
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
        return response

    static_dir = _BASE_DIR / "web" / "static"
    templates = Jinja2Templates(directory=str(_BASE_DIR / "web" / "templates"))
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    from web.api import (
        endpoints_admin_full,
        endpoints_channel_management,
        endpoints_media,
        endpoints_settings,
        endpoints_webapp_v2,
    )

    app.include_router(endpoints_webapp_v2.market_router)
    app.include_router(endpoints_webapp_v2.router)
    app.include_router(endpoints_media.router)
    app.include_router(endpoints_admin_full.router)
    app.include_router(endpoints_channel_management.router)
    app.include_router(endpoints_settings.router)

    @app.post(WEBHOOK_PATH)
    async def bot_webhook(request: Request):
        received_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not WEBHOOK_SECRET or not hmac.compare_digest(received_secret, WEBHOOK_SECRET):
            return Response(content="Forbidden", status_code=403)
        body = await request.json()
        update = Update.model_validate(body, context={"bot": bot})
        await dp.feed_update(bot, update)
        return {"ok": True}

    @app.get("/")
    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "service": "saroyliklar",
            "version": "marketplace-v8",
            "storage": "telegram-channel",
            "database": "supabase",
        }

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        return Response(status_code=204)

    @app.get("/webapp")
    async def webapp_home(request: Request):
        return templates.TemplateResponse(
            request=request,
            name="webapp.html",
            headers={"Cache-Control": "no-store, max-age=0"},
        )

    @app.get("/admin")
    async def admin_dashboard(request: Request):
        return templates.TemplateResponse(request=request, name="dashboard.html")

    @app.get("/admin/channels")
    async def admin_channels(request: Request):
        return templates.TemplateResponse(request=request, name="channel_management.html")

    @app.get("/admin/login")
    async def admin_login(request: Request):
        return templates.TemplateResponse(request=request, name="login.html")

    @app.post("/admin/login")
    async def process_admin_login(request: Request, username: str = Form(...), password: str = Form(...)):
        valid_user = ADMIN_USERNAME and hmac.compare_digest(username, ADMIN_USERNAME)
        valid_password = ADMIN_PASSWORD and hmac.compare_digest(password, ADMIN_PASSWORD)
        if valid_user and valid_password:
            response = RedirectResponse("/admin", status_code=status.HTTP_303_SEE_OTHER)
            response.set_cookie(
                ADMIN_COOKIE_NAME,
                _admin_token(),
                httponly=True,
                secure=not DEBUG,
                samesite="lax",
                max_age=24 * 60 * 60,
                path="/",
            )
            return response
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Login yoki parol noto'g'ri"},
            status_code=401,
        )

    @app.get("/admin/logout")
    async def admin_logout():
        response = RedirectResponse("/admin/login", status_code=status.HTTP_303_SEE_OTHER)
        response.delete_cookie(ADMIN_COOKIE_NAME, path="/")
        return response

    return app
