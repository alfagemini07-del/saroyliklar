from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from sqlalchemy.orm import selectinload
from typing import Optional
import logging

from database import Place, PlacePhoto, User

logger = logging.getLogger(__name__)


# =====================================================
# DO'KON (PLACE) CRUD
# =====================================================
async def create_place(
    session: AsyncSession,
    user_id: str,
    name: str,
    category: str,
    phone: str,
    description: str = None,
    lat: float = None,
    lng: float = None,
    address: str = None,
    avatar_file_id: str = None,
    avatar_url: str = None,
    cover_file_id: str = None,
    cover_url: str = None,
    working_hours: str = None,
    telegram: str = None,
    instagram: str = None,
    website: str = None
) -> Place:
    place = Place(
        user_id=user_id,
        name=name,
        category=category,
        phone=phone,
        description=description,
        lat=lat,
        lng=lng,
        address=address,
        avatar_file_id=avatar_file_id,
        avatar_url=avatar_url,
        cover_file_id=cover_file_id,
        cover_url=cover_url,
        working_hours=working_hours,
        telegram=telegram,
        instagram=instagram,
        website=website,
        status="pending"
    )
    session.add(place)
    await session.commit()
    await session.refresh(place)
    return place


async def get_place(session: AsyncSession, place_id: str) -> Optional[Place]:
    result = await session.execute(
        select(Place)
        .options(selectinload(Place.photos), selectinload(Place.user))
        .where(Place.id == place_id)
    )
    return result.scalar_one_or_none()


async def get_user_place(session: AsyncSession, user_id: str) -> Optional[Place]:
    """Foydalanuvchining do'konini oladi."""
    result = await session.execute(
        select(Place)
        .options(selectinload(Place.photos))
        .where(Place.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_all_places(
    session: AsyncSession,
    category: str = None,
    skip: int = 0,
    limit: int = 50
) -> list[Place]:
    conditions = [Place.status == "active"]
    if category and category != "all":
        conditions.append(Place.category == category)

    result = await session.execute(
        select(Place)
        .options(selectinload(Place.photos))
        .where(and_(*conditions))
        .order_by(Place.is_verified.desc(), desc(Place.created_at))
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


async def get_map_places(session: AsyncSession, category: str = None) -> list[Place]:
    """Xarita uchun do'konlarni oladi (lat/lng bilan)."""
    conditions = [
        Place.status == "active",
        Place.lat.isnot(None),
        Place.lng.isnot(None)
    ]
    if category and category != "all":
        conditions.append(Place.category == category)

    result = await session.execute(
        select(Place)
        .options(selectinload(Place.photos))
        .where(and_(*conditions))
        .limit(300)
    )
    return result.scalars().all()


async def update_place(session: AsyncSession, place_id: str, **kwargs) -> Optional[Place]:
    result = await session.execute(select(Place).where(Place.id == place_id))
    place = result.scalar_one_or_none()
    if place:
        for key, value in kwargs.items():
            if hasattr(place, key) and value is not None:
                setattr(place, key, value)
        await session.commit()
    return place


async def delete_place(session: AsyncSession, place_id: str, user_id: str) -> bool:
    result = await session.execute(
        select(Place).options(selectinload(Place.photos)).where(and_(Place.id == place_id, Place.user_id == user_id))
    )
    place = result.scalar_one_or_none()
    if place:
        storage_paths = [photo.file_id for photo in place.photos]
        storage_paths.extend(path for path in [place.avatar_file_id, place.cover_file_id] if path)
        await session.delete(place)
        await session.commit()
        from services.supabase_storage_service import get_storage
        for storage_path in storage_paths:
            await get_storage().delete(storage_path)
        return True
    return False


# =====================================================
# DO'KON RASMLARI (GALEREYA)
# =====================================================
async def add_place_photo(
    session: AsyncSession,
    place_id: str,
    file_id: str,
    caption: str = None,
    price: float = None,
    currency: str = "UZS",
    public_url: str = None,
    telegram_file_id: str = None,
    mime_type: str = "image/jpeg",
    media_type: str = "image",
    size_bytes: int = None,
) -> PlacePhoto:
    # Joriy rasmlar sonini olish
    from sqlalchemy import func
    count_result = await session.execute(
        select(func.count(PlacePhoto.id)).where(PlacePhoto.place_id == place_id)
    )
    order_num = count_result.scalar() or 0

    photo = PlacePhoto(
        place_id=place_id,
        file_id=file_id,
        public_url=public_url,
        telegram_file_id=telegram_file_id,
        mime_type=mime_type,
        media_type=media_type,
        size_bytes=size_bytes,
        caption=caption,
        price=price,
        currency=currency,
        order_num=order_num
    )
    session.add(photo)
    await session.commit()
    await session.refresh(photo)
    return photo


async def delete_place_photo(session: AsyncSession, photo_id: str, place_id: str) -> bool:
    result = await session.execute(
        select(PlacePhoto).where(
            and_(PlacePhoto.id == photo_id, PlacePhoto.place_id == place_id)
        )
    )
    photo = result.scalar_one_or_none()
    if photo:
        file_id = photo.file_id
        await session.delete(photo)
        await session.commit()
        from services.supabase_storage_service import get_storage
        await get_storage().delete(file_id)
        return True
    return False
