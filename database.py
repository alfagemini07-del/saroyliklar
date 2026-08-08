import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    select,
    text,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, relationship

from config import DATABASE_URL, DB_MAX_OVERFLOW, DB_POOL_SIZE, DB_SSL


logger = logging.getLogger(__name__)


def _async_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://"):]
    return url


_database_url = _async_database_url(DATABASE_URL)
_connect_args: dict = {}
if DB_SSL and _database_url.startswith("postgresql+asyncpg://"):
    _connect_args["ssl"] = "require"
if ":6543/" in _database_url:
    # Supavisor transaction mode does not support prepared statements.
    _connect_args["statement_cache_size"] = 0

engine = create_async_engine(
    _database_url,
    echo=False,
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
    pool_timeout=30,
    pool_recycle=300,
    pool_pre_ping=True,
    connect_args=_connect_args,
)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    full_name = Column(String(255))
    username = Column(String(255), index=True)
    phone = Column(String(32))
    region = Column(String(100))
    district = Column(String(100))
    is_blocked = Column(Boolean, default=False, nullable=False)
    is_blocked_by_user = Column(Boolean, default=False, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    balance = Column(Numeric(14, 2), default=0, nullable=False)
    ad_limit = Column(Integer, default=5, nullable=False)
    total_ad_limit = Column(Integer, default=3, nullable=False)
    channel_ad_limit = Column(Integer, default=0, nullable=False)
    referral_code = Column(String(50), unique=True, index=True)
    referred_by_id = Column(String, ForeignKey("users.id"), nullable=True)
    referral_count = Column(Integer, default=0, nullable=False)
    joined_date = Column(DateTime, default=utcnow, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    places = relationship("Place", back_populates="user", cascade="all, delete-orphan")
    ads = relationship("Ad", back_populates="user", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")


class Place(Base):
    __tablename__ = "places"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    category = Column(String(50), nullable=False, index=True)
    phone = Column(String(32), nullable=False)
    phones = Column(JSON, default=list, nullable=False)
    description = Column(Text)
    lat = Column(Float)
    lng = Column(Float)
    address = Column(String(255))
    avatar_file_id = Column(String(255))
    avatar_url = Column(Text)
    cover_file_id = Column(String(255))
    cover_url = Column(Text)
    working_hours = Column(String(100))
    telegram = Column(String(100))
    instagram = Column(String(100))
    website = Column(String(255))
    is_verified = Column(Boolean, default=False, nullable=False)
    status = Column(String(20), default="pending", nullable=False, index=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    user = relationship("User", back_populates="places")
    photos = relationship(
        "PlacePhoto",
        back_populates="place",
        cascade="all, delete-orphan",
        order_by="PlacePhoto.order_num",
    )
    ads = relationship("Ad", back_populates="place")

    __table_args__ = (Index("ix_places_map", "status", "category", "lat", "lng"),)


class PlacePhoto(Base):
    __tablename__ = "place_photos"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    place_id = Column(String, ForeignKey("places.id", ondelete="CASCADE"), nullable=False, index=True)
    file_id = Column(String(255), nullable=False)
    public_url = Column(Text)
    telegram_file_id = Column(String(255))
    mime_type = Column(String(100), default="image/jpeg")
    media_type = Column(String(20), default="image", nullable=False)
    size_bytes = Column(BigInteger)
    title = Column(String(160))
    description = Column(Text)
    caption = Column(String(200))
    price = Column(Numeric(14, 2))
    currency = Column(String(10), default="UZS", nullable=False)
    is_available = Column(Boolean, default=True, nullable=False)
    view_count = Column(Integer, default=0, nullable=False)
    order_num = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    place = relationship("Place", back_populates="photos")


class Ad(Base):
    __tablename__ = "ads"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    place_id = Column(String, ForeignKey("places.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    category = Column(String(50), nullable=False, default="other", index=True)
    price = Column(Numeric(14, 2))
    currency = Column(String(10), default="UZS", nullable=False)
    lat = Column(Float)
    lng = Column(Float)
    phone = Column(String(32))
    address = Column(String(255))
    status = Column(String(20), default="pending", nullable=False, index=True)
    view_count = Column(Integer, default=0, nullable=False)
    ai_category_confidence = Column(Float)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    user = relationship("User", back_populates="ads")
    place = relationship("Place", back_populates="ads")
    images = relationship(
        "AdImage",
        back_populates="ad",
        cascade="all, delete-orphan",
        order_by="AdImage.order_num",
    )

    __table_args__ = (
        Index("ix_ads_map", "status", "category", "lat", "lng"),
        Index("ix_ads_created", "status", "created_at"),
    )


class AdImage(Base):
    """Media attached to an ad. The legacy class name is retained for compatibility."""

    __tablename__ = "ad_images"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    ad_id = Column(String, ForeignKey("ads.id", ondelete="CASCADE"), nullable=False, index=True)
    file_id = Column(String(255), nullable=False)
    public_url = Column(Text)
    telegram_file_id = Column(String(255))
    mime_type = Column(String(100), default="image/jpeg")
    media_type = Column(String(20), default="image", nullable=False)
    size_bytes = Column(BigInteger)
    order_num = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    ad = relationship("Ad", back_populates="images")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    amount = Column(Numeric(14, 2), nullable=False)
    transaction_type = Column(String(50))
    description = Column(String(255))
    admin_note = Column(String(255))
    created_at = Column(DateTime, default=utcnow, nullable=False)

    user = relationship("User", back_populates="transactions")


class Tariff(Base):
    __tablename__ = "tariffs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False)
    price = Column(Numeric(14, 2), nullable=False)
    ad_count = Column(Integer, default=1, nullable=False)
    includes_channel = Column(Boolean, default=False, nullable=False)
    is_custom = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    target_user_id = Column(String, ForeignKey("users.id"))
    created_at = Column(DateTime, default=utcnow, nullable=False)


class ChatLog(Base):
    __tablename__ = "chat_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    message_text = Column(Text, nullable=False)
    is_from_bot = Column(Boolean, default=False, nullable=False)
    timestamp = Column(DateTime, default=utcnow, nullable=False)
    user = relationship("User")


class BotSettings(Base):
    __tablename__ = "bot_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mandatory_channel_ids = Column(JSON, default=list, nullable=False)
    post_channel_ids = Column(JSON, default=list, nullable=False)
    admin_telegram_id = Column(BigInteger)
    admin_contact_link = Column(String(255))
    require_approval = Column(Boolean, default=True, nullable=False)
    auto_post_to_channel = Column(Boolean, default=True, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


async def get_session():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def _upgrade_existing_schema() -> None:
    """Small idempotent bridge for databases created by the previous app version."""
    statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS channel_ad_limit INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE places ADD COLUMN IF NOT EXISTS avatar_url TEXT",
        "ALTER TABLE places ADD COLUMN IF NOT EXISTS cover_url TEXT",
        "ALTER TABLE ad_images ADD COLUMN IF NOT EXISTS public_url TEXT",
        "ALTER TABLE ad_images ADD COLUMN IF NOT EXISTS telegram_file_id VARCHAR(255)",
        "ALTER TABLE ad_images ADD COLUMN IF NOT EXISTS mime_type VARCHAR(100) DEFAULT 'image/jpeg'",
        "ALTER TABLE ad_images ADD COLUMN IF NOT EXISTS media_type VARCHAR(20) NOT NULL DEFAULT 'image'",
        "ALTER TABLE ad_images ADD COLUMN IF NOT EXISTS size_bytes BIGINT",
        "ALTER TABLE place_photos ADD COLUMN IF NOT EXISTS public_url TEXT",
        "ALTER TABLE place_photos ADD COLUMN IF NOT EXISTS telegram_file_id VARCHAR(255)",
        "ALTER TABLE place_photos ADD COLUMN IF NOT EXISTS mime_type VARCHAR(100) DEFAULT 'image/jpeg'",
        "ALTER TABLE place_photos ADD COLUMN IF NOT EXISTS media_type VARCHAR(20) NOT NULL DEFAULT 'image'",
        "ALTER TABLE place_photos ADD COLUMN IF NOT EXISTS size_bytes BIGINT",
        "ALTER TABLE place_photos ADD COLUMN IF NOT EXISTS title VARCHAR(160)",
        "ALTER TABLE place_photos ADD COLUMN IF NOT EXISTS description TEXT",
        "ALTER TABLE place_photos ADD COLUMN IF NOT EXISTS is_available BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE place_photos ADD COLUMN IF NOT EXISTS view_count INTEGER NOT NULL DEFAULT 0",
    ]
    async with engine.begin() as conn:
        for statement in statements:
            await conn.execute(text(statement))


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _upgrade_existing_schema()

    async with AsyncSessionLocal() as session:
        settings = await session.scalar(select(BotSettings).where(BotSettings.id == 1))
        if not settings:
            session.add(
                BotSettings(
                    id=1,
                    mandatory_channel_ids=[],
                    post_channel_ids=[],
                    admin_contact_link="https://t.me/admin",
                    require_approval=True,
                )
            )
            await session.commit()
    logger.info("Database is ready")


async def close_db() -> None:
    await engine.dispose()
