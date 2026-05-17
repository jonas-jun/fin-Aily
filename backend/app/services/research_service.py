"""
research_service.py
────────────────────
리서치 리포트 오케스트레이션 서비스.
캐시 확인 → 데이터 수집 → Map-Reduce 분석 → 캐시 저장 흐름을 담당한다.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel
from supabase import AsyncClient

from app.config import get_settings
from app.services.article_cache_service import get_or_create_ticker
from app.services.news_service import get_company_name
from app.services.research_cache_service import (
    get_cached_report,
    invalidate_report,
    save_report,
)
from app.services.research_collector import collect_all
from app.services.research_pipeline import generate_report

logger = logging.getLogger(__name__)


# ── 응답 모델 ─────────────────────────────────────────────────────────────────

class ResearchReport(BaseModel):
    symbol: str
    company_name: str
    generated_at: str
    model_version: str
    report_markdown: str
    source_metadata: dict[str, Any]


# ── 오케스트레이션 ────────────────────────────────────────────────────────────

async def get_or_generate_report(
    db: AsyncClient,
    symbol: str,
    force_refresh: bool = False,
) -> ResearchReport:
    """
    캐시 히트 시 즉시 반환, 미스 시 수집→분석→저장 후 반환.
    force_refresh=True 이면 기존 캐시를 무효화하고 재생성한다.
    """
    upper_symbol = symbol.upper()
    company = get_company_name(upper_symbol)
    ticker_id = await get_or_create_ticker(db, upper_symbol, company)

    # 강제 갱신이면 캐시 먼저 삭제
    if force_refresh:
        await invalidate_report(db, ticker_id)
        logger.info("강제 갱신: symbol=%s", upper_symbol)

    # 캐시 확인
    cached = await get_cached_report(db, ticker_id)
    if cached:
        return ResearchReport(
            symbol=upper_symbol,
            company_name=company,
            generated_at=cached["created_at"],
            model_version=cached["model_version"],
            report_markdown=cached["report_markdown"],
            source_metadata=cached["source_metadata"],
        )

    # 캐시 미스 — 수집 + 분석
    logger.info("리포트 생성 시작: symbol=%s", upper_symbol)

    try:
        filings, calls = await collect_all(upper_symbol)
    except RuntimeError as exc:
        raise exc  # COLLECTOR_SEC_FAILED / COLLECTOR_TRANSCRIPT_FAILED 전파

    settings = get_settings()
    try:
        report_markdown, model_version = await generate_report(
            ticker=upper_symbol,
            company_name=company,
            filings=filings,
            calls=calls,
            api_key=settings.gemini_api_key or None,
        )
    except RuntimeError as exc:
        raise RuntimeError("ANALYSIS_FAILED") from exc

    # source_metadata 구성
    source_metadata: dict[str, Any] = {
        "ticker": upper_symbol,
        "analysis_period": "최근 8개 공시(약 2년치) & 최근 4개 분기 컨퍼런스콜",
        "sources": {
            "sec_filings": [
                {
                    "form":             f.form,
                    "fiscal_year":      f.fiscal_year,
                    "fiscal_quarter":   f.fiscal_quarter,
                    "filing_date":      f.filing_date,
                    "period_of_report": f.period_of_report,
                    "doc_id":           f.doc_id,
                }
                for f in filings
            ],
            "earning_calls": [
                {
                    "fiscal_year":    c.fiscal_year,
                    "fiscal_quarter": c.fiscal_quarter,
                    "event_date":     c.event_date,
                    "source":         c.source,
                    "source_url":     c.source_url,
                }
                for c in calls
            ],
        },
    }

    generated_at = datetime.now(tz=timezone.utc).isoformat()

    # 캐시 저장
    await save_report(db, ticker_id, report_markdown, source_metadata, model_version)
    logger.info("리포트 생성 완료: symbol=%s", upper_symbol)

    return ResearchReport(
        symbol=upper_symbol,
        company_name=company,
        generated_at=generated_at,
        model_version=model_version,
        report_markdown=report_markdown,
        source_metadata=source_metadata,
    )
