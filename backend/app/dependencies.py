"""
dependencies.py
───────────────
FastAPI Depends 주입용 의존성 함수 모음.
"""

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
