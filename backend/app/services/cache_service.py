"""
cache_service.py
────────────────
티커 단위 종합 요약 캐시 서비스.
캐시 키: (ticker_id + 24h TTL)
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from supabase import AsyncClient

from app.services.summarization_service import DigestResult, SummaryPoint

logger = logging.getLogger(__name__)

CACHE_TTL_HOURS = 24


async def get_cached_digest(
    db: AsyncClient,
    ticker_id: int,
    lang: str = "ko",
) -> Optional[DigestResult]:
    """
    유효한 캐시(TTL 이내)가 있으면 DigestResult를 반환하고, 없으면 None을 반환한다.
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=CACHE_TTL_HOURS)

    res = (
        await db.table("ticker_summaries")
        .select("*")
        .eq("ticker_id", ticker_id)
        .gte("created_at", cutoff.isoformat())
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not res.data:
        logger.debug("캐시 미스: ticker_id=%d", ticker_id)
        return None

    row = res.data[0]
    logger.info("캐시 히트: ticker_id=%d", ticker_id)

    summary_text: str = row["summary_ko"] if lang == "ko" else (row["summary_en"] or row["summary_ko"])

    # JSON 형식(새 포맷) → 기존 bullet 텍스트(구 포맷) 순으로 시도
    try:
        raw = json.loads(summary_text)
        bullets = [SummaryPoint(point=b["point"], quote=b.get("quote", "")) for b in raw]
    except (json.JSONDecodeError, TypeError, KeyError):
        bullets = [
            SummaryPoint(point=line.lstrip("• ").strip(), quote="")
            for line in summary_text.splitlines()
            if line.strip()
        ]

    return DigestResult(
        summary=bullets,
        sentiment_score=float(row["sentiment_score"]),
        sentiment_label=row["sentiment_label"],
        model_version=row["model_version"],
        article_ids=row["article_ids"],
        article_count=row["article_count"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


async def save_digest_cache(
    db: AsyncClient,
    ticker_id: int,
    digest_ko: DigestResult,
    digest_en: Optional[DigestResult] = None,
) -> None:
    """
    종합 요약 결과를 ticker_summaries에 저장한다.
    한/영 요약을 단일 행에 저장하여 중복 캐시를 방지한다.
    """
    def to_json(points: list[SummaryPoint]) -> str:
        return json.dumps([p.model_dump() for p in points], ensure_ascii=False)

    payload = {
        "ticker_id":       ticker_id,
        "article_ids":     digest_ko.article_ids,
        "summary_ko":      to_json(digest_ko.summary),
        "summary_en":      to_json(digest_en.summary) if digest_en else None,
        "sentiment_score": float(digest_ko.sentiment_score),
        "sentiment_label": digest_ko.sentiment_label,
        "model_version":   digest_ko.model_version,
        "article_count":   digest_ko.article_count,
        "created_at":      digest_ko.created_at.isoformat(),
    }

    await db.table("ticker_summaries").insert(payload).execute()
    logger.info("캐시 저장: ticker_id=%d, count=%d", ticker_id, digest_ko.article_count)


async def invalidate_cache(db: AsyncClient, ticker_id: int) -> int:
    """특정 티커의 캐시를 전부 삭제한다. 수동 갱신/테스트용."""
    res = (
        await db.table("ticker_summaries")
        .delete()
        .eq("ticker_id", ticker_id)
        .execute()
    )
    deleted = len(res.data) if res.data else 0
    logger.info("캐시 무효화: ticker_id=%d, deleted=%d", ticker_id, deleted)
    return deleted
