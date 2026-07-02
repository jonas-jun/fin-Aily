from __future__ import annotations

from fastapi import HTTPException
from supabase import AsyncClient, acreate_client

from app.config import load_config


async def get_db() -> AsyncClient:
    config = load_config()
    if not config.supabase_url or not config.supabase_service_role_key:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "DB_NOT_CONFIGURED",
                "message": "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required for the research API.",
            },
        )
    return await acreate_client(config.supabase_url, config.supabase_service_role_key)

