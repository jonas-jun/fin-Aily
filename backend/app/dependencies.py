"""
dependencies.py
───────────────
FastAPI Depends 주입용 의존성 함수 모음.
"""

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import AsyncClient, acreate_client

from app.config import get_settings

settings = get_settings()
_bearer = HTTPBearer(auto_error=False)


# ── Supabase 클라이언트 ────────────────────────────────────────────────────────
async def get_db() -> AsyncClient:
    """요청마다 Supabase AsyncClient 인스턴스를 생성하여 주입한다."""
    client = await acreate_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
    )
    return client


# ── 인증 ──────────────────────────────────────────────────────────────────────
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncClient = Depends(get_db),
) -> dict:
    """
    Authorization: Bearer <jwt> 헤더를 검증하고 사용자 정보를 반환한다.
    토큰이 없거나 유효하지 않으면 401을 반환한다.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "로그인이 필요합니다."},
        )
    user_response = await db.auth.get_user(credentials.credentials)
    if not user_response or not user_response.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN", "message": "유효하지 않은 토큰입니다."},
        )
    return user_response.user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: AsyncClient = Depends(get_db),
) -> Optional[dict]:
    """
    토큰이 있으면 검증 후 사용자 정보를 반환하고,
    없으면 None을 반환한다 (비로그인 허용 엔드포인트용).
    """
    if credentials is None:
        return None
    try:
        user_response = await db.auth.get_user(credentials.credentials)
        return user_response.user if user_response else None
    except Exception:
        return None
