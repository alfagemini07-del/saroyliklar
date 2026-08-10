"""Backward-compatible import path for older modules.

Media is stored in the configured Telegram channel. This module intentionally
contains no Supabase credentials or HTTP storage implementation; it lets older
deploy commits use the new storage service while all callers are migrated.
"""

from services.telegram_storage_service import (
    ALLOWED_IMAGE_TYPES,
    ALLOWED_MEDIA_TYPES,
    ALLOWED_VIDEO_TYPES,
    StorageError,
    StoredMedia,
    configure_storage,
    get_storage,
    media_public_url,
    storage_public_url,
    valid_media_signature,
)


__all__ = [
    "ALLOWED_IMAGE_TYPES",
    "ALLOWED_MEDIA_TYPES",
    "ALLOWED_VIDEO_TYPES",
    "StorageError",
    "StoredMedia",
    "configure_storage",
    "get_storage",
    "media_public_url",
    "storage_public_url",
    "valid_media_signature",
]
