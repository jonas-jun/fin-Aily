"""
research_cache_service.py
──────────────────────────
ticker_research_reports 테이블 CRUD.
캐시 키: (ticker_id + 7일 TTL)
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from supabase import AsyncClient

from app.config import get_research_cache_config

logger = logging.getLogger(__name__)


async def get_cached_report(
    db: AsyncClient,
    ticker_id: int,
) -> Optional[dict[str, Any]]:
    """7일 TTL 이내의 캐시 리포트가 있으면 반환하고, 없으면 None을 반환한다."""
    ttl_hours = get_research_cache_config()
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=ttl_hours)

    res = (
        await db.table("ticker_research_reports")
        .select("*")
        .eq("ticker_id", ticker_id)
        .gte("created_at", cutoff.isoformat())
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not res.data:
        logger.debug("리서치 캐시 미스: ticker_id=%d", ticker_id)
        return None

    logger.info("리서치 캐시 히트: ticker_id=%d", ticker_id)
    row = res.data[0]
    return {
        "report_markdown": row["report_markdown"],
        "source_metadata": row["source_metadata"],
        "model_version":   row["model_version"],
        "created_at":      row["created_at"],
    }


async def save_report(
    db: AsyncClient,
    ticker_id: int,
    report_markdown: str,
    source_metadata: dict[str, Any],
    model_version: str,
) -> None:
    """리서치 리포트를 ticker_research_reports에 저장한다."""
    payload = {
        "ticker_id":       ticker_id,
        "report_markdown": report_markdown,
        "source_metadata": source_metadata,
        "model_version":   model_version,
        "created_at":      datetime.now(tz=timezone.utc).isoformat(),
    }
    await db.table("ticker_research_reports").insert(payload).execute()
    logger.info("리서치 리포트 저장: ticker_id=%d", ticker_id)


async def invalidate_report(db: AsyncClient, ticker_id: int) -> int:
    """특정 티커의 리포트 캐시를 전부 삭제한다. 수동 갱신/테스트용."""
    res = (
        await db.table("ticker_research_reports")
        .delete()
        .eq("ticker_id", ticker_id)
        .execute()
    )
    deleted = len(res.data) if res.data else 0
    logger.info("리서치 캐시 무효화: ticker_id=%d, deleted=%d", ticker_id, deleted)
    return deleted
