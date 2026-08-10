import asyncio
import os
from collections import OrderedDict
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request, Response

from services.telegram_storage_service import StorageError, get_storage, valid_media_signature


router = APIRouter(tags=["Media"])


def _media_cache_mb() -> int:
    try:
        value = int(os.getenv("MEDIA_CACHE_MB", "64"))
    except (TypeError, ValueError):
        return 64
    return max(0, min(value, 256))


MEDIA_CACHE_MB = _media_cache_mb()
_cache: OrderedDict[str, bytes] = OrderedDict()
_cache_size = 0
_cache_lock = asyncio.Lock()
_download_locks: dict[str, asyncio.Lock] = {}


async def _cached_media(media_id: str) -> bytes:
    global _cache_size
    async with _cache_lock:
        cached = _cache.get(media_id)
        if cached is not None:
            _cache.move_to_end(media_id)
            return cached
        item_lock = _download_locks.setdefault(media_id, asyncio.Lock())

    async with item_lock:
        async with _cache_lock:
            cached = _cache.get(media_id)
            if cached is not None:
                _cache.move_to_end(media_id)
                return cached
        try:
            data = await get_storage().download(media_id)
        except Exception:
            async with _cache_lock:
                _download_locks.pop(media_id, None)
            raise
        max_cache_bytes = MEDIA_CACHE_MB * 1024 * 1024
        if max_cache_bytes and len(data) <= max_cache_bytes:
            async with _cache_lock:
                previous = _cache.pop(media_id, None)
                if previous:
                    _cache_size -= len(previous)
                _cache[media_id] = data
                _cache_size += len(data)
                while _cache and _cache_size > max_cache_bytes:
                    _, removed = _cache.popitem(last=False)
                    _cache_size -= len(removed)
        async with _cache_lock:
            _download_locks.pop(media_id, None)
        return data


def _base_headers(record) -> dict[str, str]:
    etag_value = record.telegram_file_unique_id or record.id
    return {
        "Accept-Ranges": "bytes",
        "Cache-Control": "public, max-age=86400, stale-while-revalidate=604800",
        "Content-Disposition": f"inline; filename*=UTF-8''{quote(record.filename)}",
        "ETag": f'"{etag_value}"',
        "X-Content-Type-Options": "nosniff",
    }


def _byte_range(value: str, total: int) -> tuple[int, int] | None:
    if not value.startswith("bytes=") or "," in value:
        return None
    spec = value[6:].strip()
    try:
        start_text, end_text = spec.split("-", 1)
        if not start_text:
            suffix = int(end_text)
            if suffix <= 0:
                return None
            return max(0, total - suffix), total - 1
        start = int(start_text)
        end = min(int(end_text), total - 1) if end_text else total - 1
    except (TypeError, ValueError):
        return None
    if start < 0 or start >= total or end < start:
        return None
    return start, end


@router.api_route("/media/{media_id}", methods=["GET", "HEAD"])
async def serve_media(media_id: str, request: Request, sig: str = Query(..., min_length=16, max_length=128)):
    if not valid_media_signature(media_id, sig):
        raise HTTPException(status_code=403, detail="Media havolasi yaroqsiz")
    record = await get_storage().get_record(media_id)
    if not record:
        raise HTTPException(status_code=404, detail="Media topilmadi")

    headers = _base_headers(record)
    if request.headers.get("if-none-match") == headers["ETag"]:
        return Response(status_code=304, headers=headers)
    if request.method == "HEAD":
        headers["Content-Length"] = str(record.size_bytes)
        return Response(status_code=200, media_type=record.mime_type, headers=headers)

    try:
        content = await _cached_media(media_id)
    except StorageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    range_header = request.headers.get("range")
    if range_header:
        selected = _byte_range(range_header, len(content))
        if not selected:
            return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{len(content)}"})
        start, end = selected
        body = content[start:end + 1]
        headers.update(
            {
                "Content-Range": f"bytes {start}-{end}/{len(content)}",
                "Content-Length": str(len(body)),
            }
        )
        return Response(content=body, status_code=206, media_type=record.mime_type, headers=headers)

    headers["Content-Length"] = str(len(content))
    return Response(content=content, media_type=record.mime_type, headers=headers)
