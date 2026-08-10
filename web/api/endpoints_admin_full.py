import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import AD_EXPIRE_DAYS, CATEGORIES
from database import Ad, Place, PlacePhoto, Transaction, User, get_session
from services.channel_post_service import post_ad_to_channels
from services.telegram_storage_service import get_storage, media_public_url, storage_public_url


router = APIRouter(prefix="/api/admin", tags=["Admin"])
logger = logging.getLogger(__name__)


class BalancePayload(BaseModel):
    tg_id: int
    amount: float
    note: str = "Admin tomonidan"


def _date(value) -> str | None:
    return value.isoformat() if value else None


async def _user_by_tg(session: AsyncSession, telegram_id: int) -> User:
    user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
    return user


@router.get("/stats/summary")
async def stats_summary(session: AsyncSession = Depends(get_session)):
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    stats = (
        await session.execute(
            select(
                select(func.count(User.id)).scalar_subquery().label("total_users"),
                select(func.count(User.id)).where(User.created_at >= today).scalar_subquery().label("today_users"),
                select(func.count(PlacePhoto.id)).scalar_subquery().label("total_products"),
                select(func.count(User.id)).where(User.is_blocked.is_(True)).scalar_subquery().label("blocked_bot"),
                select(func.count(Place.id)).scalar_subquery().label("total_places"),
                select(func.count(Place.id)).where(Place.status == "pending").scalar_subquery().label("pending_places"),
            )
        )
    ).one()
    return {
        "total_users": stats.total_users or 0,
        "today_users": stats.today_users or 0,
        "total_products": stats.total_products or 0,
        "blocked_bot": stats.blocked_bot or 0,
        "total_places": stats.total_places or 0,
        "pending_places": stats.pending_places or 0,
    }


@router.get("/stats/chart")
async def stats_chart(days: int = Query(7, ge=1, le=90), session: AsyncSession = Depends(get_session)):
    today = datetime.utcnow().date()
    dates = [today - timedelta(days=index) for index in range(days - 1, -1, -1)]
    values = {day: 0 for day in dates}
    joined = (
        await session.execute(
            select(User.created_at).where(User.created_at >= datetime.combine(dates[0], datetime.min.time()))
        )
    ).scalars().all()
    for value in joined:
        if value and value.date() in values:
            values[value.date()] += 1
    return {
        "labels": [day.strftime("%d-%m") for day in dates],
        "datasets": {"new_users": [values[day] for day in dates]},
    }


@router.get("/users")
async def users_list(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    product_count = (
        select(func.count(PlacePhoto.id))
        .join(Place, Place.id == PlacePhoto.place_id)
        .where(Place.user_id == User.id)
        .correlate(User)
        .scalar_subquery()
    )
    store_name = (
        select(Place.name)
        .where(Place.user_id == User.id)
        .order_by(desc(Place.created_at))
        .limit(1)
        .correlate(User)
        .scalar_subquery()
    )
    rows = (
        await session.execute(
            select(
                User,
                product_count.label("product_count"),
                store_name.label("store_name"),
            )
            .order_by(desc(User.created_at))
            .offset(skip)
            .limit(limit)
        )
    ).all()
    result = []
    for user, user_product_count, user_store_name in rows:
        result.append(
            {
                "id": user.id,
                "tg_id": user.telegram_id,
                "full_name": user.full_name,
                "username": user.username,
                "phone": user.phone,
                "balance": float(user.balance or 0),
                "product_count": user_product_count or 0,
                "store_name": user_store_name,
                "is_blocked": user.is_blocked,
                "created_at": _date(user.created_at),
            }
        )
    return {"users": result, "total": await session.scalar(select(func.count(User.id))) or 0}


@router.get("/users/{tg_id}")
async def user_detail(tg_id: int, session: AsyncSession = Depends(get_session)):
    user = await _user_by_tg(session, tg_id)
    store = await session.scalar(select(Place).options(selectinload(Place.photos)).where(Place.user_id == user.id))
    return {
        "id": user.id,
        "tg_id": user.telegram_id,
        "full_name": user.full_name,
        "username": user.username,
        "phone": user.phone,
        "balance": float(user.balance or 0),
        "store_name": store.name if store else None,
        "product_count": len(store.photos) if store else 0,
        "is_blocked": user.is_blocked,
        "created_at": _date(user.created_at),
    }


@router.post("/users/{tg_id}/block")
async def block_user(tg_id: int, session: AsyncSession = Depends(get_session)):
    user = await _user_by_tg(session, tg_id)
    user.is_blocked = True
    await session.commit()
    return {"status": "success"}


@router.post("/users/{tg_id}/unblock")
async def unblock_user(tg_id: int, session: AsyncSession = Depends(get_session)):
    user = await _user_by_tg(session, tg_id)
    user.is_blocked = False
    await session.commit()
    return {"status": "success"}


@router.post("/users/{tg_id}/update-limit")
async def update_limit(
    tg_id: int,
    new_limit: int = Query(..., ge=0, le=10000),
    session: AsyncSession = Depends(get_session),
):
    user = await _user_by_tg(session, tg_id)
    user.total_ad_limit = new_limit
    await session.commit()
    return {"status": "success", "new_limit": new_limit}


@router.get("/ads/list")
async def ads_list(
    status: str | None = None,
    category: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    query = select(Ad).options(selectinload(Ad.images), selectinload(Ad.user)).order_by(desc(Ad.created_at))
    count_query = select(func.count(Ad.id))
    if status and status != "all":
        query = query.where(Ad.status == status)
        count_query = count_query.where(Ad.status == status)
    if category and category != "all":
        query = query.where(Ad.category == category)
        count_query = count_query.where(Ad.category == category)
    ads = (await session.execute(query.offset(skip).limit(limit))).scalars().all()
    return {
        "ads": [
            {
                "id": ad.id,
                "title": ad.title,
                "description": ad.description,
                "category": ad.category,
                "cat_icon": CATEGORIES.get(ad.category, CATEGORIES["other"])["icon"],
                "cat_name": CATEGORIES.get(ad.category, CATEGORIES["other"])["name"],
                "price": float(ad.price) if ad.price is not None else None,
                "currency": ad.currency,
                "phone": ad.phone,
                "address": ad.address,
                "status": ad.status,
                "view_count": ad.view_count or 0,
                "created_at": _date(ad.created_at),
                "expires_at": _date(ad.expires_at),
                "owner_name": ad.user.full_name if ad.user else None,
                "owner_phone": ad.user.phone if ad.user else None,
                "owner_telegram_id": ad.user.telegram_id if ad.user else None,
                "image": media_public_url(ad.images[0]) if ad.images else None,
            }
            for ad in ads
        ],
        "total": await session.scalar(count_query) or 0,
    }


@router.post("/ads/{ad_id}/approve")
async def approve_ad(ad_id: str, request: Request, session: AsyncSession = Depends(get_session)):
    ad = await session.scalar(
        select(Ad).options(selectinload(Ad.user), selectinload(Ad.images)).where(Ad.id == ad_id)
    )
    if not ad:
        raise HTTPException(status_code=404, detail="E'lon topilmadi")
    ad.status = "active"
    ad.expires_at = ad.expires_at or datetime.utcnow() + timedelta(days=AD_EXPIRE_DAYS)
    await session.commit()
    bot = request.app.state.bot
    if ad.user:
        try:
            await bot.send_message(ad.user.telegram_id, f"✅ E'loningiz tasdiqlandi: {ad.title}")
        except Exception as exc:
            logger.warning("Approval notification failed: %s", exc)
    try:
        await post_ad_to_channels(bot, session, ad, ad.user.username if ad.user else None)
    except Exception as exc:
        logger.warning("Channel post failed: %s", exc)
    return {"status": "success"}


@router.post("/ads/{ad_id}/reject")
async def reject_ad(ad_id: str, request: Request, session: AsyncSession = Depends(get_session)):
    ad = await session.scalar(select(Ad).options(selectinload(Ad.user)).where(Ad.id == ad_id))
    if not ad:
        raise HTTPException(status_code=404, detail="E'lon topilmadi")
    was_pending = ad.status == "pending"
    ad.status = "rejected"
    if was_pending and ad.user:
        ad.user.total_ad_limit = (ad.user.total_ad_limit or 0) + 1
    await session.commit()
    if ad.user:
        try:
            await request.app.state.bot.send_message(ad.user.telegram_id, f"❌ E'loningiz rad etildi: {ad.title}")
        except Exception as exc:
            logger.warning("Rejection notification failed: %s", exc)
    return {"status": "success"}


@router.delete("/ads/{ad_id}")
async def delete_ad(ad_id: str, session: AsyncSession = Depends(get_session)):
    ad = await session.scalar(select(Ad).options(selectinload(Ad.images)).where(Ad.id == ad_id))
    if not ad:
        raise HTTPException(status_code=404, detail="E'lon topilmadi")
    storage_paths = [item.file_id for item in ad.images]
    await session.delete(ad)
    await session.commit()
    for storage_path in storage_paths:
        await get_storage().delete(storage_path)
    return {"status": "success"}


@router.get("/places")
async def places_list(
    status: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    photo_count = (
        select(func.count(PlacePhoto.id))
        .where(PlacePhoto.place_id == Place.id)
        .correlate(Place)
        .scalar_subquery()
    )
    query = (
        select(Place, User, photo_count.label("photos_count"))
        .outerjoin(User, User.id == Place.user_id)
        .order_by(desc(Place.created_at))
    )
    count_query = select(func.count(Place.id))
    if status and status != "all":
        query = query.where(Place.status == status)
        count_query = count_query.where(Place.status == status)
    rows = (await session.execute(query.offset(skip).limit(limit))).all()
    return {
        "places": [
            {
                "id": place.id,
                "name": place.name,
                "category": place.category,
                "cat_icon": CATEGORIES.get(place.category, CATEGORIES["other"])["icon"],
                "cat_name": CATEGORIES.get(place.category, CATEGORIES["other"])["name"],
                "phone": place.phone,
                "address": place.address,
                "status": place.status,
                "is_verified": place.is_verified,
                "avatar": storage_public_url(place.avatar_file_id) or place.avatar_url,
                "created_at": _date(place.created_at),
                "owner_name": owner.full_name if owner else None,
                "owner_phone": owner.phone if owner else None,
                "owner_telegram_id": owner.telegram_id if owner else None,
                "photos_count": photos_count or 0,
                "description": place.description,
            }
            for place, owner, photos_count in rows
        ],
        "total": await session.scalar(count_query) or 0,
    }


@router.get("/dashboard")
async def dashboard_snapshot(
    days: int = Query(7, ge=1, le=90),
    session: AsyncSession = Depends(get_session),
):
    """Return the initial dashboard in one HTTP request and one DB session."""
    return {
        "summary": await stats_summary(session),
        "chart": await stats_chart(days=days, session=session),
        "users": await users_list(skip=0, limit=5, session=session),
        "places": await places_list(status=None, skip=0, limit=5, session=session),
    }


async def _place(place_id: str, session: AsyncSession) -> Place:
    place = await session.scalar(
        select(Place).options(selectinload(Place.user), selectinload(Place.photos)).where(Place.id == place_id)
    )
    if not place:
        raise HTTPException(status_code=404, detail="Joy topilmadi")
    return place


@router.get("/places/{place_id}")
async def place_detail(place_id: str, session: AsyncSession = Depends(get_session)):
    place = await _place(place_id, session)
    return {
        "id": place.id,
        "name": place.name,
        "category": place.category,
        "cat_icon": CATEGORIES.get(place.category, CATEGORIES["other"])["icon"],
        "cat_name": CATEGORIES.get(place.category, CATEGORIES["other"])["name"],
        "phone": place.phone,
        "address": place.address,
        "description": place.description,
        "status": place.status,
        "is_verified": place.is_verified,
        "avatar": storage_public_url(place.avatar_file_id) or place.avatar_url,
        "created_at": _date(place.created_at),
        "owner_name": place.user.full_name if place.user else None,
        "owner_phone": place.user.phone if place.user else None,
        "owner_telegram_id": place.user.telegram_id if place.user else None,
        "photos_count": len(place.photos),
    }


@router.post("/places/{place_id}/approve")
async def approve_place(place_id: str, request: Request, session: AsyncSession = Depends(get_session)):
    place = await _place(place_id, session)
    place.status = "active"
    await session.commit()
    if place.user:
        try:
            await request.app.state.bot.send_message(place.user.telegram_id, f"✅ Joy profilingiz tasdiqlandi: {place.name}")
        except Exception as exc:
            logger.warning("Place notification failed: %s", exc)
    return {"status": "success"}


@router.post("/places/{place_id}/reject")
async def reject_place(place_id: str, request: Request, session: AsyncSession = Depends(get_session)):
    place = await _place(place_id, session)
    place.status = "rejected"
    await session.commit()
    if place.user:
        try:
            await request.app.state.bot.send_message(place.user.telegram_id, f"❌ Joy profilingiz rad etildi: {place.name}")
        except Exception as exc:
            logger.warning("Place notification failed: %s", exc)
    return {"status": "success"}


@router.post("/places/{place_id}/verify")
async def verify_place(place_id: str, session: AsyncSession = Depends(get_session)):
    place = await _place(place_id, session)
    place.status = "active"
    place.is_verified = True
    await session.commit()
    return {"status": "success"}


@router.delete("/places/{place_id}")
async def delete_place(place_id: str, session: AsyncSession = Depends(get_session)):
    place = await _place(place_id, session)
    storage_paths = [item.file_id for item in place.photos]
    if place.avatar_file_id:
        storage_paths.append(place.avatar_file_id)
    if place.cover_file_id:
        storage_paths.append(place.cover_file_id)
    await session.delete(place)
    await session.commit()
    for storage_path in storage_paths:
        await get_storage().delete(storage_path)
    return {"status": "success"}


@router.get("/finance/summary")
async def finance_summary(session: AsyncSession = Depends(get_session)):
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return {
        "total_balance": float(await session.scalar(select(func.sum(User.balance))) or 0),
        "today_added": float(
            await session.scalar(
                select(func.sum(Transaction.amount)).where(
                    Transaction.transaction_type == "admin_add", Transaction.created_at >= today
                )
            )
            or 0
        ),
    }


@router.get("/finance/history")
async def finance_history(
    limit: int = Query(30, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    transactions = (
        await session.execute(
            select(Transaction).options(selectinload(Transaction.user)).order_by(desc(Transaction.created_at)).limit(limit)
        )
    ).scalars().all()
    return {
        "history": [
            {
                "user_name": transaction.user.full_name if transaction.user else None,
                "tg_id": transaction.user.telegram_id if transaction.user else None,
                "amount": float(transaction.amount),
                "type": "add" if transaction.amount >= 0 else "deduct",
                "note": transaction.description or transaction.admin_note or "",
                "created_at": _date(transaction.created_at),
            }
            for transaction in transactions
        ]
    }


@router.post("/finance/add-balance")
async def add_balance(payload: BalancePayload, session: AsyncSession = Depends(get_session)):
    if payload.amount <= 0:
        raise HTTPException(status_code=422, detail="Miqdor musbat bo'lishi kerak")
    user = await _user_by_tg(session, payload.tg_id)
    user.balance = (user.balance or 0) + payload.amount
    session.add(
        Transaction(
            user_id=user.id,
            amount=payload.amount,
            transaction_type="admin_add",
            description=payload.note,
            admin_note=payload.note,
        )
    )
    await session.commit()
    return {"status": "success", "new_balance": float(user.balance)}
