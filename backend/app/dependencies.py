"""
dependencies.py
───────────────
FastAPI Depends 주입용 의존성 함수 모음.
"""

from supabase import AsyncClient, acreate_client

from app.config import get_settings

settings = get_settings()


# ── Supabase 클라이언트 ────────────────────────────────────────────────────────
async def create_db_client() -> AsyncClient:
    """Supabase AsyncClient 인스턴스를 새로 생성한다.

    FastAPI Depends 경로는 get_db()를 쓰고, BackgroundTasks처럼 Depends를
    쓸 수 없는 경로(예: research_router.run_research_job)는 이 함수를 직접 호출한다.
    """
    return await acreate_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
    )


async def get_db() -> AsyncClient:
    """요청마다 Supabase AsyncClient 인스턴스를 생성하여 주입한다."""
    return await create_db_client()
