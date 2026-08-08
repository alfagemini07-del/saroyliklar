import logging
import mimetypes
import re
import uuid
from dataclasses import dataclass
from urllib.parse import quote

import httpx

from config import (
    MAX_UPLOAD_MB,
    SUPABASE_STORAGE_BUCKET,
    SUPABASE_STORAGE_KEY,
    SUPABASE_URL,
)


logger = logging.getLogger(__name__)
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/webm", "video/quicktime"}
ALLOWED_MEDIA_TYPES = ALLOWED_IMAGE_TYPES | ALLOWED_VIDEO_TYPES


@dataclass(slots=True)
class StoredMedia:
    file_id: str
    public_url: str
    mime_type: str
    media_type: str
    size_bytes: int
    name: str
    telegram_file_id: str | None = None


class StorageError(RuntimeError):
    pass


def _safe_object_path(filename: str, prefix: str, mime_type: str) -> str:
    original = filename or "media"
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", original.rsplit(".", 1)[0]).strip("-")[:50]
    extension = mimetypes.guess_extension(mime_type) or ".bin"
    if extension == ".jpe":
        extension = ".jpg"
    folder = re.sub(r"[^A-Za-z0-9_-]+", "-", prefix).strip("-") or "media"
    return f"{folder}/{stem or 'media'}-{uuid.uuid4().hex}{extension}"


def storage_public_url(file_id: str, mime_type: str = "image/jpeg") -> str:
    del mime_type
    if not file_id:
        return ""
    if file_id.startswith(("http://", "https://", "/")):
        return file_id
    if not SUPABASE_URL or not SUPABASE_STORAGE_BUCKET:
        return ""
    bucket = quote(SUPABASE_STORAGE_BUCKET, safe="")
    path = quote(file_id, safe="/")
    return f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/public/{bucket}/{path}"


def media_public_url(media) -> str | None:
    if not media:
        return None
    public_url = getattr(media, "public_url", None)
    if public_url:
        return public_url
    file_id = getattr(media, "file_id", None)
    return storage_public_url(file_id) if file_id else None


class SupabaseStorage:
    @property
    def configured(self) -> bool:
        return bool(SUPABASE_URL and SUPABASE_STORAGE_KEY and SUPABASE_STORAGE_BUCKET)

    def _headers(self, **extra: str) -> dict[str, str]:
        if not self.configured:
            raise StorageError("Supabase Storage sozlanmagan")
        headers = {
            "apikey": SUPABASE_STORAGE_KEY,
            **extra,
        }
        # New sb_secret keys are opaque API keys, while legacy service_role keys are JWTs.
        if not SUPABASE_STORAGE_KEY.startswith("sb_secret_"):
            headers["Authorization"] = f"Bearer {SUPABASE_STORAGE_KEY}"
        return headers

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
            return str(payload.get("message") or payload.get("error") or payload)
        except ValueError:
            return response.text[:300] or f"HTTP {response.status_code}"

    async def upload(
        self,
        content: bytes,
        filename: str,
        mime_type: str,
        prefix: str = "media",
    ) -> StoredMedia:
        if mime_type not in ALLOWED_MEDIA_TYPES:
            raise StorageError("Faqat JPG, PNG, WEBP, GIF, MP4, WEBM va MOV fayllari qabul qilinadi")
        max_bytes = MAX_UPLOAD_MB * 1024 * 1024
        if not content:
            raise StorageError("Yuklangan fayl bo'sh")
        if len(content) > max_bytes:
            raise StorageError(f"Fayl hajmi {MAX_UPLOAD_MB} MB dan oshmasligi kerak")

        object_path = _safe_object_path(filename, prefix, mime_type)
        bucket = quote(SUPABASE_STORAGE_BUCKET, safe="")
        encoded_path = quote(object_path, safe="/")
        url = f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/{bucket}/{encoded_path}"
        headers = self._headers(
            **{
                "Content-Type": mime_type,
                "Cache-Control": "3600",
                "x-upsert": "false",
            }
        )
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=20.0)) as client:
                response = await client.post(url, headers=headers, content=content)
        except httpx.HTTPError as exc:
            raise StorageError("Supabase Storage bilan aloqa o'rnatilmadi") from exc
        if response.status_code not in {200, 201}:
            raise StorageError(f"Supabase Storage: {self._error_message(response)}")

        return StoredMedia(
            file_id=object_path,
            public_url=storage_public_url(object_path, mime_type),
            mime_type=mime_type,
            media_type="video" if mime_type.startswith("video/") else "image",
            size_bytes=len(content),
            name=object_path.rsplit("/", 1)[-1],
        )

    async def delete(self, file_id: str) -> None:
        if not file_id or file_id.startswith(("http://", "https://", "/")):
            return
        bucket = quote(SUPABASE_STORAGE_BUCKET, safe="")
        url = f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/{bucket}"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.request(
                    "DELETE",
                    url,
                    headers=self._headers(**{"Content-Type": "application/json"}),
                    json={"prefixes": [file_id]},
                )
            if response.status_code not in {200, 204}:
                logger.warning("Supabase fayli o'chirilmadi %s: %s", file_id, self._error_message(response))
        except (httpx.HTTPError, StorageError) as exc:
            logger.warning("Supabase faylini o'chirishda xato %s: %s", file_id, exc)

    async def download(self, file_id: str) -> bytes:
        if not file_id:
            raise StorageError("Fayl yo'li berilmagan")
        bucket = quote(SUPABASE_STORAGE_BUCKET, safe="")
        path = quote(file_id, safe="/")
        url = f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/authenticated/{bucket}/{path}"
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                response = await client.get(url, headers=self._headers())
        except httpx.HTTPError as exc:
            raise StorageError("Supabase faylini yuklab bo'lmadi") from exc
        if response.status_code != 200:
            raise StorageError(f"Supabase Storage: {self._error_message(response)}")
        return response.content


_storage = SupabaseStorage()


def get_storage() -> SupabaseStorage:
    return _storage
