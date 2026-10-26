"""Xác thực người dùng bằng access token của Supabase Auth.

Không bao giờ nhận user_id từ body/query: owner_id luôn lấy từ token đã được Supabase xác minh.
"""
import logging
from uuid import UUID

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

log = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> UUID:
    if credentials is None:
        if settings.dev_user_id is not None:
            return settings.dev_user_id
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Thiếu token xác thực.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        response = httpx.get(
            f"{settings.supabase_url}/auth/v1/user",
            headers={"apikey": settings.supabase_service_key, "Authorization": f"Bearer {credentials.credentials}"},
            timeout=10,
        )
    except httpx.HTTPError as exc:
        log.warning("Không kết nối được Supabase Auth: %s", exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Không xác thực được, thử lại sau.") from exc

    if response.status_code != 200:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Token không hợp lệ hoặc đã hết hạn.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return UUID(response.json()["id"])
