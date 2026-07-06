"""
dependencies.py
───────────────
FastAPI Depends 주입용 의존성 함수 모음.
"""

from fastapi import Depends, Header, HTTPException
from supabase import AsyncClient, acreate_client

from app.config import get_settings

settings = get_settings()


# ── Supabase 클라이언트 ────────────────────────────────────────────────────────
async def get_db() -> AsyncClient:
    """요청마다 Supabase AsyncClient 인스턴스를 생성하여 주입한다."""
    client = await acreate_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
    )
    return client


# ── 인증 (현재 미사용) ──────────────────────────────────────────────────────────
# 개인 사용 모드로 전환하며 라우터에서 연결을 끊었다. 재도입 시 각 라우터 엔드포인트에
# `user: dict = Depends(get_current_user)`를 다시 추가하면 된다.
async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncClient = Depends(get_db),
) -> dict:
    """Validate ``Authorization: Bearer <supabase_access_token>``. Anonymous access is rejected."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "로그인이 필요합니다."},
        )
    token = authorization.split(" ", 1)[1].strip()
    try:
        result = await db.auth.get_user(token)
        user = result.user
    except Exception:
        user = None
    if user is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_TOKEN", "message": "유효하지 않은 세션입니다."},
        )
    return {"id": user.id, "email": user.email}
