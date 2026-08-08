import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import CATEGORIES, MAX_PLACE_PHOTOS
from database import Place, PlacePhoto, User, get_session
from services.supabase_storage_service import StorageError, get_storage, media_public_url, storage_public_url
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


def _number(value: str | None, *, minimum: float | None = None) -> float | None:
    if value is None or not value.strip():
        return None
    try:
        number = float(value.replace(" ", "").replace(",", "."))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Raqam formati noto'g'ri") from exc
    if minimum is not None and number < minimum:
        raise HTTPException(status_code=422, detail="Qiymat manfiy bo'lishi mumkin emas")
    return number


def _coordinates(lat: str | None, lng: str | None, *, required: bool = False) -> tuple[float | None, float | None]:
    if not lat and not lng:
        if required:
            raise HTTPException(status_code=422, detail="Do'kon joylashuvini xaritada belgilang")
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
        raise HTTPException(status_code=502, detail="Faylni saqlashda xatolik yuz berdi") from exc
    return stored


async def _delete_uploaded(items: list) -> None:
    for item in items:
        if item:
            await get_storage().delete(item.file_id)


def _own_product(product: PlacePhoto) -> dict:
    return {
        "id": product.id,
        "title": product.title or product.caption or "Mahsulot",
        "description": product.description,
        "price": float(product.price) if product.price is not None else None,
        "currency": product.currency,
        "media": media_public_url(product),
        "media_type": product.media_type or "image",
        "is_available": product.is_available,
        "view_count": product.view_count or 0,
        "created_at": product.created_at.isoformat() if product.created_at else None,
    }


def _own_store(store: Place) -> dict:
    return {
        "id": store.id,
        "name": store.name,
        "description": store.description,
        "category": store.category,
        "phone": store.phone,
        "address": store.address,
        "lat": store.lat,
        "lng": store.lng,
        "working_hours": store.working_hours,
        "telegram": store.telegram,
        "instagram": store.instagram,
        "website": store.website,
        "avatar": store.avatar_url or storage_public_url(store.avatar_file_id),
        "cover": store.cover_url or storage_public_url(store.cover_file_id),
        "status": store.status,
        "is_verified": store.is_verified,
    }


@router.get("/me")
async def get_profile(
    tg_user: dict = Depends(telegram_user),
    session: AsyncSession = Depends(get_session),
):
    user = await _db_user(tg_user, session)
    store = await session.scalar(
        select(Place).options(selectinload(Place.photos)).where(Place.user_id == user.id)
    )
    return {
        "user": {
            "telegram_id": user.telegram_id,
            "full_name": user.full_name,
            "username": user.username,
            "phone": user.phone,
            "region": user.region,
        },
        "store": _own_store(store) if store else None,
        "products": [_own_product(product) for product in store.photos] if store else [],
    }


@router.post("/store")
async def create_store(
    name: str = Form(...),
    category: str = Form("other"),
    phone: str = Form(...),
    description: str = Form(""),
    address: str = Form(...),
    lat: str = Form(...),
    lng: str = Form(...),
    working_hours: str = Form(""),
    telegram: str = Form(""),
    instagram: str = Form(""),
    website: str = Form(""),
    avatar: UploadFile | None = File(default=None),
    cover: UploadFile | None = File(default=None),
    tg_user: dict = Depends(telegram_user),
    session: AsyncSession = Depends(get_session),
):
    user = await _db_user(tg_user, session)
    if await session.scalar(select(func.count(Place.id)).where(Place.user_id == user.id)):
        raise HTTPException(status_code=409, detail="Sizda allaqachon do'kon mavjud")
    clean_name = name.strip()
    clean_phone = phone.strip()
    clean_address = address.strip()
    if len(clean_name) < 2:
        raise HTTPException(status_code=422, detail="Do'kon nomini kiriting")
    if len(clean_phone) < 5:
        raise HTTPException(status_code=422, detail="Telefon raqamini kiriting")
    if len(clean_address) < 3:
        raise HTTPException(status_code=422, detail="Do'kon manzilini kiriting")
    lat_value, lng_value = _coordinates(lat, lng, required=True)
    avatar_items = await _upload_files([avatar] if avatar else [], "store-avatar", 1)
    try:
        cover_items = await _upload_files([cover] if cover else [], "store-cover", 1)
    except Exception:
        await _delete_uploaded(avatar_items)
        raise
    avatar_media = avatar_items[0] if avatar_items else None
    cover_media = cover_items[0] if cover_items else None
    store = Place(
        user_id=user.id,
        name=clean_name[:150],
        category=category if category in CATEGORIES else "other",
        phone=clean_phone[:32],
        description=description.strip()[:4000] or None,
        address=clean_address[:255],
        lat=lat_value,
        lng=lng_value,
        working_hours=working_hours.strip()[:100] or None,
        telegram=telegram.strip().lstrip("@")[:100] or None,
        instagram=instagram.strip().lstrip("@")[:100] or None,
        website=website.strip()[:255] or None,
        avatar_file_id=avatar_media.file_id if avatar_media else None,
        avatar_url=avatar_media.public_url if avatar_media else None,
        cover_file_id=cover_media.file_id if cover_media else None,
        cover_url=cover_media.public_url if cover_media else None,
        status="pending",
    )
    session.add(store)
    try:
        await session.commit()
        await session.refresh(store)
    except Exception:
        await session.rollback()
        await _delete_uploaded([avatar_media, cover_media])
        raise
    return {"status": "success", "store": _own_store(store), "message": "Do'kon tekshiruvga yuborildi"}


@router.put("/store")
async def update_store(
    name: str | None = Form(default=None),
    category: str | None = Form(default=None),
    phone: str | None = Form(default=None),
    description: str | None = Form(default=None),
    address: str | None = Form(default=None),
    lat: str | None = Form(default=None),
    lng: str | None = Form(default=None),
    working_hours: str | None = Form(default=None),
    telegram: str | None = Form(default=None),
    instagram: str | None = Form(default=None),
    website: str | None = Form(default=None),
    avatar: UploadFile | None = File(default=None),
    cover: UploadFile | None = File(default=None),
    tg_user: dict = Depends(telegram_user),
    session: AsyncSession = Depends(get_session),
):
    user = await _db_user(tg_user, session)
    store = await session.scalar(select(Place).where(Place.user_id == user.id))
    if not store:
        raise HTTPException(status_code=404, detail="Do'kon topilmadi")
    if name is not None and len(name.strip()) >= 2:
        store.name = name.strip()[:150]
    if category is not None:
        store.category = category if category in CATEGORIES else "other"
    if phone is not None and phone.strip():
        store.phone = phone.strip()[:32]
    if description is not None:
        store.description = description.strip()[:4000] or None
    if address is not None and address.strip():
        store.address = address.strip()[:255]
    if lat is not None or lng is not None:
        store.lat, store.lng = _coordinates(lat, lng, required=True)
    if working_hours is not None:
        store.working_hours = working_hours.strip()[:100] or None
    if telegram is not None:
        store.telegram = telegram.strip().lstrip("@")[:100] or None
    if instagram is not None:
        store.instagram = instagram.strip().lstrip("@")[:100] or None
    if website is not None:
        store.website = website.strip()[:255] or None

    uploaded_avatar = (await _upload_files([avatar], "store-avatar", 1))[0] if avatar and avatar.filename else None
    try:
        uploaded_cover = (await _upload_files([cover], "store-cover", 1))[0] if cover and cover.filename else None
    except Exception:
        await _delete_uploaded([uploaded_avatar])
        raise
    old_paths = []
    if uploaded_avatar:
        if store.avatar_file_id:
            old_paths.append(store.avatar_file_id)
        store.avatar_file_id = uploaded_avatar.file_id
        store.avatar_url = uploaded_avatar.public_url
    if uploaded_cover:
        if store.cover_file_id:
            old_paths.append(store.cover_file_id)
        store.cover_file_id = uploaded_cover.file_id
        store.cover_url = uploaded_cover.public_url
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        await _delete_uploaded([uploaded_avatar, uploaded_cover])
        raise
    for path in old_paths:
        await get_storage().delete(path)
    return {"status": "success", "store": _own_store(store), "message": "Do'kon ma'lumotlari yangilandi"}


@router.post("/products")
async def add_product(
    title: str = Form(...),
    description: str = Form(""),
    price: str = Form(""),
    currency: str = Form("UZS"),
    media: UploadFile = File(...),
    tg_user: dict = Depends(telegram_user),
    session: AsyncSession = Depends(get_session),
):
    user = await _db_user(tg_user, session)
    store = await session.scalar(
        select(Place).options(selectinload(Place.photos)).where(Place.user_id == user.id)
    )
    if not store:
        raise HTTPException(status_code=404, detail="Avval do'kon oching")
    if len(store.photos) >= MAX_PLACE_PHOTOS:
        raise HTTPException(status_code=422, detail=f"Ko'pi bilan {MAX_PLACE_PHOTOS} ta mahsulot qo'shiladi")
    clean_title = title.strip()
    if len(clean_title) < 2:
        raise HTTPException(status_code=422, detail="Mahsulot nomini kiriting")
    uploaded = (await _upload_files([media], "product", 1))[0]
    product = PlacePhoto(
        place_id=store.id,
        file_id=uploaded.file_id,
        public_url=uploaded.public_url,
        mime_type=uploaded.mime_type,
        media_type=uploaded.media_type,
        size_bytes=uploaded.size_bytes,
        title=clean_title[:160],
        caption=clean_title[:200],
        description=description.strip()[:2000] or None,
        price=_number(price, minimum=0),
        currency=currency if currency in {"UZS", "USD"} else "UZS",
        is_available=True,
        order_num=max((item.order_num for item in store.photos), default=-1) + 1,
    )
    session.add(product)
    try:
        await session.commit()
        await session.refresh(product)
    except Exception:
        await session.rollback()
        await get_storage().delete(uploaded.file_id)
        raise
    return {"status": "success", "product": _own_product(product), "message": "Mahsulot qo'shildi"}


@router.put("/products/{product_id}")
async def update_product(
    product_id: str,
    title: str = Form(...),
    description: str = Form(""),
    price: str = Form(""),
    currency: str = Form("UZS"),
    is_available: bool = Form(True),
    media: UploadFile | None = File(default=None),
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
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")
    clean_title = title.strip()
    if len(clean_title) < 2:
        raise HTTPException(status_code=422, detail="Mahsulot nomini kiriting")
    product.title = clean_title[:160]
    product.caption = clean_title[:200]
    product.description = description.strip()[:2000] or None
    product.price = _number(price, minimum=0)
    product.currency = currency if currency in {"UZS", "USD"} else "UZS"
    product.is_available = is_available
    uploaded = (await _upload_files([media], "product", 1))[0] if media and media.filename else None
    old_path = None
    if uploaded:
        old_path = product.file_id
        product.file_id = uploaded.file_id
        product.public_url = uploaded.public_url
        product.mime_type = uploaded.mime_type
        product.media_type = uploaded.media_type
        product.size_bytes = uploaded.size_bytes
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        await _delete_uploaded([uploaded])
        raise
    if old_path:
        await get_storage().delete(old_path)
    return {"status": "success", "product": _own_product(product), "message": "Mahsulot yangilandi"}


@router.delete("/products/{product_id}")
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
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")
    storage_path = product.file_id
    await session.delete(product)
    await session.commit()
    await get_storage().delete(storage_path)
    return {"status": "success"}
