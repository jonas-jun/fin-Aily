"""
tickers_router.py
─────────────────
티커 자동완성 검색 엔드포인트.
"""

import asyncio

import yfinance as yf
from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter(prefix="/tickers", tags=["tickers"])


class TickerResult(BaseModel):
    symbol: str
    name: str
    exchange: str | None = None


class SearchResponse(BaseModel):
    results: list[TickerResult]


@router.get(
    "/search",
    response_model=SearchResponse,
    summary="티커 자동완성 검색",
)
async def search_tickers(
    q: str = Query(..., min_length=1, max_length=20, description="검색어"),
):
    """
    티커 심볼 또는 회사명으로 검색한다. 인증 불필요.
    Rate Limit: 30회/분 (미들웨어에서 처리).
    yfinance Search API를 사용한다.
    """
    search = await asyncio.to_thread(yf.Search, q, max_results=10)

    keyword = q.upper()
    results = []
    for quote in search.quotes:
        symbol = quote.get("symbol", "")
        if symbol.upper() != keyword:
            continue
        if quote.get("quoteType") != "EQUITY":
            continue
        name = quote.get("shortname") or quote.get("longname") or ""
        exchange = quote.get("exchange")
        results.append(TickerResult(symbol=symbol, name=name, exchange=exchange))

    return SearchResponse(results=results)
