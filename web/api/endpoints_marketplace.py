from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import CATEGORIES
from database import Place, PlacePhoto, get_session
from services.supabase_storage_service import media_public_url, storage_public_url


router = APIRouter(prefix="/api/market", tags=["Marketplace"])


def _price(value, currency: str) -> dict | None:
    if value is None:
        return None
    number = float(value)
    formatted = f"${number:,.0f}" if currency == "USD" else f"{number:,.0f} so'm".replace(",", " ")
    return {"value": number, "currency": currency, "formatted": formatted}


def _store_card(store: Place) -> dict:
    category = CATEGORIES.get(store.category, CATEGORIES["other"])
    avatar = store.avatar_url or storage_public_url(store.avatar_file_id)
    return {
        "id": store.id,
        "name": store.name,
        "description": store.description,
        "category": store.category,
        "category_name": category["name"],
        "category_icon": category["icon"],
        "category_color": category["color"],
        "avatar": avatar,
        "cover": store.cover_url or storage_public_url(store.cover_file_id),
        "phone": store.phone,
        "address": store.address,
        "lat": store.lat,
        "lng": store.lng,
        "working_hours": store.working_hours,
        "telegram": store.telegram,
        "instagram": store.instagram,
        "website": store.website,
        "is_verified": store.is_verified,
        "status": store.status,
    }


def _product_card(product: PlacePhoto, store: Place | None = None) -> dict:
    store = store or product.place
    category = CATEGORIES.get(store.category, CATEGORIES["other"])
    title = product.title or product.caption or "Mahsulot"
    return {
        "id": product.id,
        "title": title,
        "description": product.description,
        "price": _price(product.price, product.currency),
        "media": media_public_url(product),
        "media_type": product.media_type or "image",
        "is_available": product.is_available,
        "view_count": product.view_count or 0,
        "created_at": product.created_at.isoformat() if product.created_at else None,
        "category": store.category,
        "category_name": category["name"],
        "category_color": category["color"],
        "store": {
            "id": store.id,
            "name": store.name,
            "avatar": store.avatar_url or storage_public_url(store.avatar_file_id),
            "address": store.address,
            "phone": store.phone,
            "telegram": store.telegram,
            "is_verified": store.is_verified,
        },
    }


def _bounds(conditions: list, north, south, east, west) -> None:
    values = (north, south, east, west)
    if all(value is not None for value in values):
        if south > north or west > east:
            raise HTTPException(status_code=422, detail="Xarita chegaralari noto'g'ri")
        conditions.extend([Place.lat.between(south, north), Place.lng.between(west, east)])


@router.get("/categories")
async def categories():
    return [{"id": key, **value} for key, value in CATEGORIES.items()]


@router.get("/products")
async def products(
    category: str = Query("all"),
    q: str = Query("", max_length=100),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
):
    conditions = [Place.status == "active", PlacePhoto.is_available.is_(True)]
    if category != "all":
        conditions.append(Place.category == category)
    if q.strip():
        term = f"%{q.strip()}%"
        conditions.append(
            or_(
                PlacePhoto.title.ilike(term),
                PlacePhoto.caption.ilike(term),
                PlacePhoto.description.ilike(term),
                Place.name.ilike(term),
                Place.address.ilike(term),
            )
        )
    query = (
        select(PlacePhoto)
        .join(Place, Place.id == PlacePhoto.place_id)
        .options(selectinload(PlacePhoto.place))
        .where(and_(*conditions))
    )
    result = await session.execute(query.order_by(desc(PlacePhoto.created_at)).offset(skip).limit(limit))
    total = await session.scalar(
        select(func.count(PlacePhoto.id)).join(Place, Place.id == PlacePhoto.place_id).where(and_(*conditions))
    ) or 0
    items = [_product_card(product) for product in result.scalars()]
    return {"products": items, "total": total, "has_more": skip + len(items) < total}


@router.get("/stores")
async def stores(
    category: str = Query("all"),
    q: str = Query("", max_length=100),
    limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    conditions = [Place.status == "active"]
    if category != "all":
        conditions.append(Place.category == category)
    if q.strip():
        term = f"%{q.strip()}%"
        conditions.append(or_(Place.name.ilike(term), Place.description.ilike(term), Place.address.ilike(term)))
    result = await session.execute(
        select(Place)
        .where(and_(*conditions))
        .order_by(Place.is_verified.desc(), desc(Place.created_at))
        .limit(limit)
    )
    return {"stores": [_store_card(store) for store in result.scalars()]}


@router.get("/map")
async def map_stores(
    category: str = Query("all"),
    north: float | None = None,
    south: float | None = None,
    east: float | None = None,
    west: float | None = None,
    session: AsyncSession = Depends(get_session),
):
    conditions = [Place.status == "active", Place.lat.is_not(None), Place.lng.is_not(None)]
    if category != "all":
        conditions.append(Place.category == category)
    _bounds(conditions, north, south, east, west)
    result = await session.execute(
        select(Place).where(and_(*conditions)).order_by(Place.is_verified.desc(), desc(Place.created_at)).limit(500)
    )
    return {"stores": [_store_card(store) for store in result.scalars()]}


@router.get("/products/{product_id}")
async def product_detail(product_id: str, session: AsyncSession = Depends(get_session)):
    product = await session.scalar(
        select(PlacePhoto)
        .join(Place, Place.id == PlacePhoto.place_id)
        .options(selectinload(PlacePhoto.place))
        .where(PlacePhoto.id == product_id, Place.status == "active", PlacePhoto.is_available.is_(True))
    )
    if not product:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")
    product.view_count = (product.view_count or 0) + 1
    await session.commit()
    return _product_card(product)


@router.get("/stores/{store_id}")
async def store_detail(store_id: str, session: AsyncSession = Depends(get_session)):
    store = await session.scalar(
        select(Place).options(selectinload(Place.photos)).where(Place.id == store_id, Place.status == "active")
    )
    if not store:
        raise HTTPException(status_code=404, detail="Do'kon topilmadi")
    data = _store_card(store)
    data["products"] = [_product_card(product, store) for product in store.photos if product.is_available]
    return data
