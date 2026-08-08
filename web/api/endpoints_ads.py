from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import CATEGORIES
from database import Ad, Place, User, get_session
from services.supabase_storage_service import media_public_url, storage_public_url


router = APIRouter(prefix="/api/ads", tags=["Public ads"])


def _price(price, currency: str) -> dict | None:
    if price is None:
        return None
    value = float(price)
    return {
        "value": value,
        "currency": currency,
        "formatted": f"${value:,.0f}" if currency == "USD" else f"{value:,.0f} so'm".replace(",", " "),
    }


def _media(item) -> dict:
    return {
        "id": item.id,
        "url": media_public_url(item),
        "type": item.media_type or "image",
        "mime_type": item.mime_type or "image/jpeg",
    }


def _ad_card(ad: Ad) -> dict:
    category = CATEGORIES.get(ad.category, CATEGORIES["other"])
    first_media = ad.images[0] if ad.images else None
    return {
        "id": ad.id,
        "kind": "ad",
        "title": ad.title,
        "description": ad.description,
        "category": ad.category,
        "category_name": category["name"],
        "category_icon": category["icon"],
        "category_color": category["color"],
        "price": _price(ad.price, ad.currency),
        "thumbnail": media_public_url(first_media),
        "media_type": first_media.media_type if first_media else None,
        "phone": ad.phone,
        "address": ad.address,
        "lat": ad.lat,
        "lng": ad.lng,
        "status": ad.status,
        "view_count": ad.view_count or 0,
        "created_at": ad.created_at.isoformat() if ad.created_at else None,
    }


def _place_card(place: Place) -> dict:
    category = CATEGORIES.get(place.category, CATEGORIES["other"])
    avatar = place.avatar_url or (storage_public_url(place.avatar_file_id) if place.avatar_file_id else None)
    return {
        "id": place.id,
        "kind": "place",
        "title": place.name,
        "name": place.name,
        "description": place.description,
        "category": place.category,
        "category_name": category["name"],
        "category_icon": category["icon"],
        "category_color": category["color"],
        "thumbnail": avatar,
        "phone": place.phone,
        "address": place.address,
        "lat": place.lat,
        "lng": place.lng,
        "is_verified": place.is_verified,
        "status": place.status,
    }


def _map_bounds(conditions: list, model, north, south, east, west) -> None:
    values = (north, south, east, west)
    if all(value is not None for value in values):
        if south > north or west > east:
            raise HTTPException(status_code=422, detail="Xarita chegaralari noto'g'ri")
        conditions.extend(
            [
                model.lat.between(south, north),
                model.lng.between(west, east),
            ]
        )


@router.get("/meta/categories")
async def get_categories():
    return [
        {"id": key, **value}
        for key, value in CATEGORIES.items()
    ]


@router.get("/map")
async def get_map_items(
    category: str = Query("all"),
    north: float | None = None,
    south: float | None = None,
    east: float | None = None,
    west: float | None = None,
    limit: int = Query(400, ge=1, le=600),
    session: AsyncSession = Depends(get_session),
):
    ad_conditions = [Ad.status == "active", Ad.lat.is_not(None), Ad.lng.is_not(None)]
    place_conditions = [Place.status == "active", Place.lat.is_not(None), Place.lng.is_not(None)]
    if category != "all":
        ad_conditions.append(Ad.category == category)
        place_conditions.append(Place.category == category)
    _map_bounds(ad_conditions, Ad, north, south, east, west)
    _map_bounds(place_conditions, Place, north, south, east, west)

    ad_result = await session.execute(
        select(Ad)
        .options(selectinload(Ad.images))
        .where(and_(*ad_conditions))
        .order_by(desc(Ad.created_at))
        .limit(limit)
    )
    place_result = await session.execute(
        select(Place)
        .where(and_(*place_conditions))
        .order_by(Place.is_verified.desc(), desc(Place.created_at))
        .limit(limit)
    )
    return {
        "items": [*(_ad_card(ad) for ad in ad_result.scalars()), *(_place_card(place) for place in place_result.scalars())],
    }


@router.get("/list")
async def get_ads_list(
    category: str = Query("all"),
    q: str = Query("", max_length=100),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
):
    conditions = [Ad.status == "active"]
    if category != "all":
        conditions.append(Ad.category == category)
    if q.strip():
        term = f"%{q.strip()}%"
        conditions.append(or_(Ad.title.ilike(term), Ad.description.ilike(term), Ad.address.ilike(term)))

    result = await session.execute(
        select(Ad)
        .options(selectinload(Ad.images))
        .where(and_(*conditions))
        .order_by(desc(Ad.created_at))
        .offset(skip)
        .limit(limit)
    )
    total = await session.scalar(select(func.count(Ad.id)).where(and_(*conditions))) or 0
    ads = [_ad_card(ad) for ad in result.scalars()]
    return {"ads": ads, "total": total, "has_more": skip + len(ads) < total}


@router.get("/places")
async def get_places(
    category: str = Query("all"),
    limit: int = Query(30, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    conditions = [Place.status == "active"]
    if category != "all":
        conditions.append(Place.category == category)
    result = await session.execute(
        select(Place)
        .where(and_(*conditions))
        .order_by(Place.is_verified.desc(), desc(Place.created_at))
        .limit(limit)
    )
    return {"places": [_place_card(place) for place in result.scalars()]}


@router.get("/place/{place_id}")
async def get_place_detail(place_id: str, session: AsyncSession = Depends(get_session)):
    place = await session.scalar(
        select(Place)
        .options(selectinload(Place.photos))
        .where(Place.id == place_id, Place.status == "active")
    )
    if not place:
        raise HTTPException(status_code=404, detail="Joy topilmadi")
    data = _place_card(place)
    data.update(
        {
            "working_hours": place.working_hours,
            "telegram": place.telegram,
            "instagram": place.instagram,
            "website": place.website,
            "cover": place.cover_url,
            "photos": [
                {
                    **_media(photo),
                    "caption": photo.caption,
                    "price": _price(photo.price, photo.currency),
                }
                for photo in place.photos
            ],
        }
    )
    return data


@router.get("/{ad_id}")
async def get_ad_detail(ad_id: str, session: AsyncSession = Depends(get_session)):
    ad = await session.scalar(
        select(Ad)
        .options(selectinload(Ad.images), selectinload(Ad.user), selectinload(Ad.place))
        .where(Ad.id == ad_id, Ad.status == "active")
    )
    if not ad:
        raise HTTPException(status_code=404, detail="E'lon topilmadi")
    ad.view_count = (ad.view_count or 0) + 1
    await session.commit()
    data = _ad_card(ad)
    data.update(
        {
            "media": [_media(item) for item in ad.images],
            "seller": {
                "name": ad.user.full_name if ad.user else None,
                "username": ad.user.username if ad.user else None,
            },
            "place": _place_card(ad.place) if ad.place else None,
        }
    )
    return data
