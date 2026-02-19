"""
article_cache_service.py
────────────────────────
뉴스 기사 DB 캐싱 서비스.
- 1시간 TTL로 기사를 캐싱하여 외부 API 중복 호출을 방지한다.
- ticker 조회/생성 헬퍼를 제공한다.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from supabase import AsyncClient

from app.config import get_cache_config
from app.services.news_service import RawArticle

logger = logging.getLogger(__name__)


async def get_or_create_ticker(
    db: AsyncClient,
    symbol: str,
    name: str = "",
    exchange: Optional[str] = None,
) -> int:
    """ticker를 조회하고, 없으면 생성한 뒤 ticker_id를 반환한다."""
    res = (
        await db.table("tickers")
        .select("id")
        .eq("symbol", symbol)
        .limit(1)
        .execute()
    )
    if res.data:
        return res.data[0]["id"]

    insert_res = (
        await db.table("tickers")
        .insert({"symbol": symbol, "name": name or symbol, "exchange": exchange})
        .execute()
    )
    return insert_res.data[0]["id"]


async def get_cached_articles(
    db: AsyncClient,
    ticker_id: int,
    limit: int = 10,
) -> Optional[list[dict]]:

    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=get_cache_config().article_ttl_hours)

    res = (
        await db.table("news_articles")
        .select("*")
        .eq("ticker_id", ticker_id)
        .gte("created_at", cutoff.isoformat())
        .order("published_at", desc=True)
        .limit(limit)
        .execute()
    )

    if not res.data:
        logger.debug("기사 캐시 미스: ticker_id=%d", ticker_id)
        return None

    logger.info("기사 캐시 히트: ticker_id=%d, count=%d", ticker_id, len(res.data))
    return res.data


async def save_articles(
    db: AsyncClient,
    ticker_id: int,
    articles: list[RawArticle],
) -> list[dict]:
    """
    수집된 기사를 news_articles에 저장한다.
    url 중복 시 무시(upsert)하고 저장된 행들을 반환한다.
    """
    rows = [
        {
            "ticker_id": ticker_id,
            "title": a.title,
            "url": a.url,
            "source": a.source,
            "published_at": a.published_at.isoformat() if a.published_at else None,
            "raw_content": a.raw_content,
        }
        for a in articles
        if a.url  # URL 없는 기사는 UNIQUE 제약 충돌 방지를 위해 저장 제외
    ]
    if not rows:
        return []

    res = (
        await db.table("news_articles")
        .upsert(rows, on_conflict="url", ignore_duplicates=True)
        .execute()
    )

    logger.info("기사 저장: ticker_id=%d, saved=%d", ticker_id, len(res.data))
    return res.data
