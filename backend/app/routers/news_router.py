"""
news_router.py
──────────────
뉴스 조회 라우터.

응답 구조:
  - digest: 종합 요약(bullet) + Sentiment  ← 상단
  - articles: 기사 제목/링크 목록          ← 하단 (summary 필드 없음)
"""

import asyncio
import logging
from typing import Optional

import yfinance as yf

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.config import get_settings
from app.dependencies import get_db
from app.services.cache_service import get_cached_digest, save_digest_cache
from app.services.news_service import fetch_articles
from app.services.summarization_service import ArticleInput, DigestResult, SummaryPoint, summarize_articles

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/news", tags=["news"])


# ── 응답 스키마 ────────────────────────────────────────────────────────────────
class SentimentOut(BaseModel):
    score: float
    label: str


class DigestOut(BaseModel):
    summary: list[SummaryPoint]
    sentiment: SentimentOut
    based_on_articles: int


class ArticleOut(BaseModel):
    id: int
    title: str
    source: str
    url: str
    published_at: str


class NewsResponse(BaseModel):
    symbol: str
    company_name: str
    last_updated: str
    digest: DigestOut
    articles: list[ArticleOut]


# ── 엔드포인트 ─────────────────────────────────────────────────────────────────
@router.get(
    "/{symbol}",
    response_model=NewsResponse,
    summary="종목 최신 뉴스 + AI 종합 요약",
)
async def get_news(
    symbol: str,
    limit: int = Query(default=10, ge=1, le=20),
    lang: str = Query(default="ko", pattern="^(ko|en)$"),
    db=Depends(get_db),
):
    upper_symbol = symbol.upper()

    # 1. 티커 조회
    ticker = await _get_ticker(db, upper_symbol)
    if not ticker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TICKER_NOT_FOUND", "message": f"'{symbol}' 종목을 찾을 수 없습니다."},
        )

    ticker_id: int = ticker["id"]
    company_name: str = ticker["name"]

    # 2. DB에 기사 없으면 외부 수집 후 저장
    db_articles = await _get_db_articles(db, ticker_id, limit)
    if not db_articles:
        raw_articles = await fetch_articles(upper_symbol, limit)
        if not raw_articles:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "NO_NEWS", "message": f"'{symbol}'에 대한 최신 뉴스가 없습니다."},
            )
        db_articles = await _upsert_articles(db, ticker_id, raw_articles)
        if not db_articles:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "NO_NEWS", "message": f"'{symbol}'에 대한 최신 뉴스가 없습니다."},
            )

    last_updated = db_articles[0]["published_at"] or db_articles[0]["created_at"]

    # 3. 캐시 확인
    digest: Optional[DigestResult] = await get_cached_digest(db, ticker_id, lang)

    # 4. 캐시 미스 → LLM 종합 요약
    if digest is None:
        settings = get_settings()
        provider = settings.summarization_provider
        api_key = (
            settings.gemini_api_key if provider == "gemini" else settings.anthropic_api_key
        ) or None

        inputs = [
            ArticleInput(
                id=a["id"],
                title=a["title"],
                source=a["source"] or "",
                content=a.get("raw_content") or "",
            )
            for a in db_articles
        ]
        try:
            digest = await summarize_articles(
                symbol=upper_symbol,
                company_name=company_name,
                articles=inputs,
                lang=lang,
                api_key=api_key,
                provider=provider,
            )
        except Exception as exc:
            logger.error("요약 실패: symbol=%s, %s", symbol, exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "SUMMARIZATION_FAILED", "message": "AI 요약 생성에 실패했습니다. 잠시 후 다시 시도해주세요."},
            ) from exc

        # 캐시 저장 (실패해도 응답은 정상 반환)
        try:
            await save_digest_cache(db, ticker_id, digest)
        except Exception as exc:
            logger.warning("캐시 저장 실패(무시): %s", exc)

    # 5. 응답 조립
    return NewsResponse(
        symbol=upper_symbol,
        company_name=company_name,
        last_updated=str(last_updated),
        digest=DigestOut(
            summary=digest.summary,
            sentiment=SentimentOut(score=digest.sentiment_score, label=digest.sentiment_label),
            based_on_articles=digest.article_count,
        ),
        articles=[
            ArticleOut(
                id=a["id"],
                title=a["title"],
                source=a["source"] or "",
                url=a["url"],
                published_at=str(a["published_at"] or ""),
            )
            for a in db_articles
        ],
    )


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────
async def _get_ticker(db, symbol: str) -> Optional[dict]:
    res = await db.table("tickers").select("id, symbol, name").eq("symbol", symbol).limit(1).execute()
    if res.data:
        return res.data[0]

    # DB에 없으면 yfinance로 조회 후 자동 등록
    info = await asyncio.to_thread(lambda: yf.Ticker(symbol).info)
    name = info.get("longName") or info.get("shortName")
    if not name:
        return None

    insert_res = await db.table("tickers").insert({
        "symbol": symbol,
        "name": name,
        "exchange": info.get("exchange"),
        "sector": info.get("sector"),
    }).execute()

    return insert_res.data[0] if insert_res.data else None


async def _get_db_articles(db, ticker_id: int, limit: int) -> list[dict]:
    res = (
        await db.table("news_articles")
        .select("id, title, url, source, published_at, raw_content, created_at")
        .eq("ticker_id", ticker_id)
        .order("published_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


async def _upsert_articles(db, ticker_id: int, raw_articles) -> list[dict]:
    """외부 수집 기사를 DB에 upsert하고 저장된 행을 반환한다."""
    rows = [
        {
            "ticker_id":    ticker_id,
            "title":        a.title,
            "url":          a.url,
            "source":       a.source,
            "published_at": a.published_at.isoformat() if a.published_at else None,
            "raw_content":  a.raw_content,
        }
        for a in raw_articles
        if a.url  # url 없는 항목 제외
    ]
    if not rows:
        return []

    await (
        db.table("news_articles")
        .upsert(rows, on_conflict="url")
        .execute()
    )
    # 저장 후 DB에서 다시 조회 (id 포함)
    return await _get_db_articles(db, ticker_id, len(rows))
