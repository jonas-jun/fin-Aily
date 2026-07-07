"""
ticker_service.py
──────────────────
실제 상장 종목 티커 조회/생성 서비스.
yfinance 프로필(회사명·거래소·섹터) 조회 후 DB에 upsert하며, 동시 요청 경합 시
insert 실패를 select 재시도로 흡수한다.

시장 전체를 나타내는 의사(疑似) 티커(예: "MARKET")는 실제 종목이 아니므로
yfinance 조회가 무의미하다 — 이 경우 article_cache_service.get_or_create_ticker()를
직접 사용한다.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from supabase import AsyncClient

logger = logging.getLogger(__name__)


async def ensure_ticker(db: AsyncClient, symbol: str) -> dict[str, Any]:
    """실제 종목 티커를 조회하고, 없으면 yfinance 프로필과 함께 생성한다."""
    normalized = symbol.upper().strip()
    existing = (
        await db.table("tickers")
        .select("*")
        .eq("symbol", normalized)
        .limit(1)
        .execute()
    )
    if existing.data:
        return existing.data[0]

    profile = await asyncio.to_thread(_lookup_ticker_profile, normalized)
    payload = {
        "symbol": normalized,
        "name": profile.get("name") or normalized,
        "exchange": profile.get("exchange"),
        "sector": profile.get("sector"),
    }
    try:
        inserted = await db.table("tickers").insert(payload).execute()
        if inserted.data:
            return inserted.data[0]
    except Exception:
        logger.info("Ticker insert raced or failed; retrying select: %s", normalized)

    retry = (
        await db.table("tickers")
        .select("*")
        .eq("symbol", normalized)
        .limit(1)
        .execute()
    )
    if retry.data:
        return retry.data[0]
    raise RuntimeError(f"Unable to create ticker row for {normalized}")


def _lookup_ticker_profile(symbol: str) -> dict[str, Any]:
    try:
        import yfinance as yf  # type: ignore

        info = yf.Ticker(symbol).info or {}
        return {
            "name": info.get("longName") or info.get("shortName"),
            "exchange": info.get("exchange"),
            "sector": info.get("sector"),
        }
    except Exception:
        return {"name": symbol, "exchange": None, "sector": None}
