from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func, or_
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone, timedelta
from typing import Optional
import logging

from database import User, Ad, AdImage, Place
from config import AD_EXPIRE_DAYS

logger = logging.getLogger(__name__)


# =====================================================
# FOYDALANUVCHI
# =====================================================
async def get_user(session: AsyncSession, telegram_id: int) -> Optional[User]:
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


async def create_or_update_user(
    session: AsyncSession,
    telegram_id: int,
    full_name: str,
    username: str = None
) -> User:
    user = await get_user(session, telegram_id)
    if not user:
        user = User(
            telegram_id=telegram_id,
            full_name=full_name,
            username=username,
            referral_code=f"ref_{telegram_id}"
        )
        session.add(user)
        await session.flush()
    else:
        if full_name:
            user.full_name = full_name
        if username:
            user.username = username
    return user


# =====================================================
# E'LONLAR
# =====================================================
async def create_ad(
    session: AsyncSession,
    user_id: str,
    title: str,
    description: str,
    category: str,
    price: float = None,
    currency: str = "UZS",
    lat: float = None,
    lng: float = None,
    phone: str = None,
    address: str = None,
    place_id: str = None,
    ai_confidence: float = None,
    image_file_ids: list = None,
    media_items: list = None,
    require_approval: bool = True
) -> Ad:
    expires = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=AD_EXPIRE_DAYS)
    status = "pending" if require_approval else "active"

    ad = Ad(
        user_id=user_id,
        place_id=place_id,
        title=title,
        description=description,
        category=category,
        price=price,
        currency=currency,
        lat=lat,
        lng=lng,
        phone=phone,
        address=address,
        status=status,
        ai_category_confidence=ai_confidence,
        expires_at=expires
    )
    session.add(ad)
    await session.flush()

    items = media_items or image_file_ids or []
    for i, item in enumerate(items):
        if isinstance(item, str):
            image = AdImage(
                ad_id=ad.id,
                file_id=item,
                public_url=item if item.startswith("http") else None,
                order_num=i,
            )
        else:
            image = AdImage(
                ad_id=ad.id,
                file_id=item.file_id,
                public_url=item.public_url,
                telegram_file_id=getattr(item, "telegram_file_id", None),
                mime_type=item.mime_type,
                media_type=item.media_type,
                size_bytes=item.size_bytes,
                order_num=i,
            )
        session.add(image)

    await session.commit()
    await session.refresh(ad)
    return ad


async def get_ad(session: AsyncSession, ad_id: str) -> Optional[Ad]:
    result = await session.execute(
        select(Ad)
        .options(selectinload(Ad.images), selectinload(Ad.user))
        .where(Ad.id == ad_id)
    )
    return result.scalar_one_or_none()


async def get_map_ads(
    session: AsyncSession,
    category: str = None,
    lat: float = None,
    lng: float = None,
    radius_km: float = 50.0
) -> list[Ad]:
    """Xarita uchun faol e'lonlarni oladi (lat/lng bilan)."""
    conditions = [
        Ad.status == "active",
        Ad.lat.isnot(None),
        Ad.lng.isnot(None)
    ]
    if category and category != "all":
        conditions.append(Ad.category == category)

    result = await session.execute(
        select(Ad)
        .options(selectinload(Ad.images))
        .where(and_(*conditions))
        .order_by(desc(Ad.created_at))
        .limit(200)
    )
    return result.scalars().all()


async def get_ads_list(
    session: AsyncSession,
    category: str = None,
    skip: int = 0,
    limit: int = 20
) -> list[Ad]:
    """Galereya ko'rinishi uchun e'lonlar ro'yxati."""
    conditions = [Ad.status == "active"]
    if category and category != "all":
        conditions.append(Ad.category == category)

    result = await session.execute(
        select(Ad)
        .options(selectinload(Ad.images), selectinload(Ad.user))
        .where(and_(*conditions))
        .order_by(desc(Ad.created_at))
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


async def get_user_ads(session: AsyncSession, user_id: str) -> list[Ad]:
    result = await session.execute(
        select(Ad)
        .options(selectinload(Ad.images))
        .where(Ad.user_id == user_id)
        .order_by(desc(Ad.created_at))
    )
    return result.scalars().all()


async def get_pending_ads(session: AsyncSession) -> list[Ad]:
    result = await session.execute(
        select(Ad)
        .options(selectinload(Ad.images), selectinload(Ad.user))
        .where(Ad.status == "pending")
        .order_by(Ad.created_at)
    )
    return result.scalars().all()


async def approve_ad(session: AsyncSession, ad_id: str) -> Optional[Ad]:
    result = await session.execute(select(Ad).where(Ad.id == ad_id))
    ad = result.scalar_one_or_none()
    if ad:
        ad.status = "active"
        await session.commit()
    return ad


async def reject_ad(session: AsyncSession, ad_id: str, reason: str = None) -> Optional[Ad]:
    result = await session.execute(select(Ad).where(Ad.id == ad_id))
    ad = result.scalar_one_or_none()
    if ad:
        ad.status = "rejected"
        await session.commit()
    return ad


async def delete_ad(session: AsyncSession, ad_id: str, user_id: str) -> bool:
    result = await session.execute(
        select(Ad).options(selectinload(Ad.images)).where(and_(Ad.id == ad_id, Ad.user_id == user_id))
    )
    ad = result.scalar_one_or_none()
    if ad:
        storage_paths = [item.file_id for item in ad.images]
        await session.delete(ad)
        await session.commit()
        from services.telegram_storage_service import get_storage
        for storage_path in storage_paths:
            await get_storage().delete(storage_path)
        return True
    return False


# =====================================================
# STATISTIKA
# =====================================================
async def get_stats(session: AsyncSession) -> dict:
    total_users   = await session.scalar(select(func.count(User.id)))
    total_ads     = await session.scalar(select(func.count(Ad.id)))
    active_ads    = await session.scalar(select(func.count(Ad.id)).where(Ad.status == "active"))
    pending_ads   = await session.scalar(select(func.count(Ad.id)).where(Ad.status == "pending"))
    blocked_users = await session.scalar(select(func.count(User.id)).where(User.is_blocked == True))
    total_places  = await session.scalar(select(func.count(Place.id)))

    return {
        "total_users":   total_users   or 0,
        "total_ads":     total_ads     or 0,
        "active_ads":    active_ads    or 0,
        "pending_ads":   pending_ads   or 0,
        "blocked_users": blocked_users or 0,
        "total_places":  total_places  or 0,
    }
