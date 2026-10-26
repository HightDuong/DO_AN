"""Lưu file PDF gốc lên Supabase Storage qua REST API (bucket private)."""
import logging

import httpx

from app.config import settings

log = logging.getLogger(__name__)


class StorageError(Exception):
    """Lỗi khi thao tác với Supabase Storage."""


def _headers() -> dict[str, str]:
    key = settings.supabase_service_key
    headers = {"apikey": key}
    # Key dạng mới (sb_secret_...) không phải JWT, chỉ gửi qua header apikey.
    # Key service_role kiểu cũ (JWT) cần thêm Authorization.
    if not key.startswith("sb_"):
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _storage_url(path: str) -> str:
    return f"{settings.supabase_url}/storage/v1/{path}"


def _create_bucket() -> None:
    response = httpx.post(
        _storage_url("bucket"),
        json={"id": settings.storage_bucket, "name": settings.storage_bucket, "public": False},
        headers=_headers(),
        timeout=30,
    )
    if response.status_code >= 400 and "already exists" not in response.text.lower():
        raise StorageError(f"Không tạo được bucket '{settings.storage_bucket}': {response.text[:300]}")
    log.info("Đã tạo bucket private '%s' trên Supabase Storage", settings.storage_bucket)


def _post_object(path: str, data: bytes) -> httpx.Response:
    return httpx.post(
        _storage_url(f"object/{settings.storage_bucket}/{path}"),
        content=data,
        headers={**_headers(), "Content-Type": "application/pdf", "x-upsert": "false"},
        timeout=120,
    )


def upload_pdf(path: str, data: bytes) -> None:
    """Upload PDF tới `<bucket>/<path>`. Tự tạo bucket private nếu chưa có."""
    try:
        response = _post_object(path, data)
        if response.status_code in (400, 404) and "bucket not found" in response.text.lower():
            _create_bucket()
            response = _post_object(path, data)
    except httpx.HTTPError as exc:
        raise StorageError(f"Không kết nối được Supabase Storage: {exc}") from exc
    if response.status_code >= 400:
        raise StorageError(f"Upload lên Supabase Storage thất bại ({response.status_code}): {response.text[:300]}")


def delete_pdf(path: str) -> None:
    """Xóa file, bỏ qua lỗi (dùng để dọn dẹp khi bước sau thất bại)."""
    try:
        httpx.request(
            "DELETE",
            _storage_url(f"object/{settings.storage_bucket}"),
            json={"prefixes": [path]},
            headers=_headers(),
            timeout=30,
        )
    except httpx.HTTPError:
        log.warning("Không xóa được file %s trên Storage", path, exc_info=True)
