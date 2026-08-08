import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import AD_EXPIRE_DAYS, CATEGORIES, MAX_AD_IMAGES, MAX_PLACE_PHOTOS
from database import Ad, AdImage, BotSettings, Place, PlacePhoto, User, get_session
from services.supabase_storage_service import StorageError, get_storage, media_public_url
from services.telegram_auth import telegram_user


router = APIRouter(prefix="/api/webapp", tags=["Telegram WebApp"])
logger = logging.getLogger(__name__)


async def _db_user(tg_user: dict, session: AsyncSession) -> User:
    user = await session.scalar(select(User).where(User.telegram_id == int(tg_user["id"])))
    if not user:
        raise HTTPException(status_code=403, detail="Avval botda /start buyrug'ini bosing")
    if user.is_blocked:
        raise HTTPException(status_code=403, detail="Hisobingiz bloklangan")
    return user


def _number(value: str, *, minimum: float | None = None) -> float | None:
    if not value or not value.strip():
        return None
    try:
        number = float(value.replace(" ", "").replace(",", "."))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Raqam formati noto'g'ri") from exc
    if minimum is not None and number < minimum:
        raise HTTPException(status_code=422, detail="Qiymat manfiy bo'lishi mumkin emas")
    return number


def _coordinates(lat: str, lng: str) -> tuple[float | None, float | None]:
    if not lat and not lng:
        return None, None
    lat_value = _number(lat)
    lng_value = _number(lng)
    if lat_value is None or lng_value is None:
        raise HTTPException(status_code=422, detail="Lokatsiyani to'liq belgilang")
    if not -90 <= lat_value <= 90 or not -180 <= lng_value <= 180:
        raise HTTPException(status_code=422, detail="Lokatsiya koordinatalari noto'g'ri")
    return lat_value, lng_value


async def _upload_files(files: list[UploadFile], prefix: str, max_count: int) -> list:
    valid = [file for file in files if file and file.filename]
    if len(valid) > max_count:
        raise HTTPException(status_code=422, detail=f"Ko'pi bilan {max_count} ta media yuklang")
    stored = []
    try:
        for file in valid:
            content = await file.read()
            stored.append(
                await get_storage().upload(
                    content,
                    file.filename or "media",
                    (file.content_type or "application/octet-stream").lower(),
                    prefix=prefix,
                )
            )
    except StorageError as exc:
        for item in stored:
            await get_storage().delete(item.file_id)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        for item in stored:
            await get_storage().delete(item.file_id)
        logger.exception("Supabase Storage upload failed")
        raise HTTPException(status_code=502, detail="Faylni Supabase Storage'ga yuklab bo'lmadi") from exc
    return stored


@router.get("/me")
async def get_profile(
    tg_user: dict = Depends(telegram_user),
    session: AsyncSession = Depends(get_session),
):
    user = await _db_user(tg_user, session)
    ads = (
        await session.execute(
            select(Ad)
            .options(selectinload(Ad.images))
            .where(Ad.user_id == user.id)
            .order_by(desc(Ad.created_at))
            .limit(50)
        )
    ).scalars().all()
    place = await session.scalar(
        select(Place).options(selectinload(Place.photos)).where(Place.user_id == user.id)
    )
    return {
        "user": {
            "telegram_id": user.telegram_id,
            "full_name": user.full_name,
            "username": user.username,
            "phone": user.phone,
            "region": user.region,
            "balance": float(user.balance or 0),
            "remaining_ads": user.total_ad_limit or 0,
            "referral_count": user.referral_count or 0,
        },
        "ads": [
            {
                "id": ad.id,
                "title": ad.title,
                "status": ad.status,
                "price": float(ad.price) if ad.price is not None else None,
                "currency": ad.currency,
                "thumbnail": media_public_url(ad.images[0]) if ad.images else None,
                "created_at": ad.created_at.isoformat() if ad.created_at else None,
            }
            for ad in ads
        ],
        "place": (
            {
                "id": place.id,
                "name": place.name,
                "status": place.status,
                "thumbnail": place.avatar_url,
                "products_count": len(place.photos),
            }
            if place
            else None
        ),
    }


@router.post("/ads")
async def create_ad(
    title: str = Form(...),
    description: str = Form(""),
    category: str = Form("other"),
    price: str = Form(""),
    currency: str = Form("UZS"),
    phone: str = Form(""),
    address: str = Form(""),
    lat: str = Form(""),
    lng: str = Form(""),
    media: list[UploadFile] = File(default=[]),
    tg_user: dict = Depends(telegram_user),
    session: AsyncSession = Depends(get_session),
):
    user = await _db_user(tg_user, session)
    title = title.strip()
    if len(title) < 3 or len(title) > 200:
        raise HTTPException(status_code=422, detail="Sarlavha 3-200 belgi bo'lishi kerak")
    if (user.total_ad_limit or 0) <= 0:
        raise HTTPException(status_code=429, detail="E'lon limitingiz tugagan")
    if category not in CATEGORIES:
        category = "other"
    if currency not in {"UZS", "USD"}:
        currency = "UZS"
    lat_value, lng_value = _coordinates(lat, lng)
    uploaded = await _upload_files(media, "ad", MAX_AD_IMAGES)

    settings = await session.scalar(select(BotSettings).where(BotSettings.id == 1))
    require_approval = settings.require_approval if settings else True
    ad = Ad(
        user_id=user.id,
        title=title,
        description=description.strip()[:4000] or None,
        category=category,
        price=_number(price, minimum=0),
        currency=currency,
        phone=phone.strip()[:32] or user.phone,
        address=address.strip()[:255] or None,
        lat=lat_value,
        lng=lng_value,
        status="pending" if require_approval else "active",
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=AD_EXPIRE_DAYS),
    )
    session.add(ad)
    await session.flush()
    for order, item in enumerate(uploaded):
        session.add(
            AdImage(
                ad_id=ad.id,
                file_id=item.file_id,
                public_url=item.public_url,
                mime_type=item.mime_type,
                media_type=item.media_type,
                size_bytes=item.size_bytes,
                order_num=order,
            )
        )
    user.total_ad_limit -= 1
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        for item in uploaded:
            await get_storage().delete(item.file_id)
        raise
    return {
        "status": "success",
        "id": ad.id,
        "ad_status": ad.status,
        "remaining_ads": user.total_ad_limit,
        "message": "E'lon tekshiruvga yuborildi" if require_approval else "E'lon joylandi",
    }


@router.post("/places")
async def create_place(
    name: str = Form(...),
    category: str = Form("other"),
    phone: str = Form(...),
    description: str = Form(""),
    address: str = Form(""),
    lat: str = Form(""),
    lng: str = Form(""),
    working_hours: str = Form(""),
    telegram: str = Form(""),
    instagram: str = Form(""),
    avatar: UploadFile | None = File(default=None),
    tg_user: dict = Depends(telegram_user),
    session: AsyncSession = Depends(get_session),
):
    user = await _db_user(tg_user, session)
    if await session.scalar(select(func.count(Place.id)).where(Place.user_id == user.id)):
        raise HTTPException(status_code=409, detail="Sizda allaqachon joy profili mavjud")
    lat_value, lng_value = _coordinates(lat, lng)
    uploaded = await _upload_files([avatar] if avatar else [], "place-avatar", 1)
    avatar_media = uploaded[0] if uploaded else None
    place = Place(
        user_id=user.id,
        name=name.strip()[:150],
        category=category if category in CATEGORIES else "other",
        phone=phone.strip()[:32],
        description=description.strip()[:4000] or None,
        address=address.strip()[:255] or None,
        lat=lat_value,
        lng=lng_value,
        working_hours=working_hours.strip()[:100] or None,
        telegram=telegram.strip().lstrip("@")[:100] or None,
        instagram=instagram.strip()[:100] or None,
        avatar_file_id=avatar_media.file_id if avatar_media else None,
        avatar_url=avatar_media.public_url if avatar_media else None,
        status="pending",
    )
    session.add(place)
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        if avatar_media:
            await get_storage().delete(avatar_media.file_id)
        raise
    return {"status": "success", "id": place.id, "message": "Joy profili tekshiruvga yuborildi"}


@router.post("/places/products")
async def add_product(
    caption: str = Form(""),
    price: str = Form(""),
    currency: str = Form("UZS"),
    media: UploadFile = File(...),
    tg_user: dict = Depends(telegram_user),
    session: AsyncSession = Depends(get_session),
):
    user = await _db_user(tg_user, session)
    place = await session.scalar(
        select(Place).options(selectinload(Place.photos)).where(Place.user_id == user.id)
    )
    if not place:
        raise HTTPException(status_code=404, detail="Avval joy profilini yarating")
    if len(place.photos) >= MAX_PLACE_PHOTOS:
        raise HTTPException(status_code=422, detail=f"Ko'pi bilan {MAX_PLACE_PHOTOS} ta media qo'shiladi")
    uploaded = (await _upload_files([media], "place-product", 1))[0]
    next_order = max((item.order_num for item in place.photos), default=-1) + 1
    product = PlacePhoto(
        place_id=place.id,
        file_id=uploaded.file_id,
        public_url=uploaded.public_url,
        mime_type=uploaded.mime_type,
        media_type=uploaded.media_type,
        size_bytes=uploaded.size_bytes,
        caption=caption.strip()[:200] or None,
        price=_number(price, minimum=0),
        currency=currency if currency in {"UZS", "USD"} else "UZS",
        order_num=next_order,
    )
    session.add(product)
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        await get_storage().delete(uploaded.file_id)
        raise
    return {"status": "success", "id": product.id, "message": "Media qo'shildi"}


@router.delete("/ads/{ad_id}")
async def delete_ad(
    ad_id: str,
    tg_user: dict = Depends(telegram_user),
    session: AsyncSession = Depends(get_session),
):
    user = await _db_user(tg_user, session)
    ad = await session.scalar(
        select(Ad).options(selectinload(Ad.images)).where(Ad.id == ad_id, Ad.user_id == user.id)
    )
    if not ad:
        raise HTTPException(status_code=404, detail="E'lon topilmadi")
    storage_paths = [item.file_id for item in ad.images]
    await session.delete(ad)
    await session.commit()
    for storage_path in storage_paths:
        await get_storage().delete(storage_path)
    return {"status": "success"}


@router.delete("/places/products/{product_id}")
async def delete_product(
    product_id: str,
    tg_user: dict = Depends(telegram_user),
    session: AsyncSession = Depends(get_session),
):
    user = await _db_user(tg_user, session)
    product = await session.scalar(
        select(PlacePhoto)
        .join(Place, Place.id == PlacePhoto.place_id)
        .where(PlacePhoto.id == product_id, Place.user_id == user.id)
    )
    if not product:
        raise HTTPException(status_code=404, detail="Media topilmadi")
    file_id = product.file_id
    await session.delete(product)
    await session.commit()
    await get_storage().delete(file_id)
    return {"status": "success"}
