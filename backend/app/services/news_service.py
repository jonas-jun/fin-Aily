"""
news_service.py
───────────────
뉴스 수집 서비스.
yfinance → RSS(MarketWatch) → NewsAPI 순으로 수집을 시도한다.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import feedparser
import yfinance as yf

logger = logging.getLogger(__name__)

RSS_FEEDS = {
    "MarketWatch": "https://feeds.marketwatch.com/marketwatch/topstories/",
    "Yahoo Finance": "https://finance.yahoo.com/rss/",
}


@dataclass
class RawArticle:
    title: str
    url: str
    source: str
    published_at: Optional[datetime]
    raw_content: str


async def fetch_articles(symbol: str, limit: int = 10) -> list[RawArticle]:
    """
    티커 심볼에 대한 최신 뉴스를 수집한다.
    yfinance 우선, 실패 시 RSS 피드를 사용한다.

    Args:
        symbol: 티커 심볼 (예: AAPL)
        limit:  가져올 기사 최대 수

    Returns:
        RawArticle 목록 (최신순)
    """
    articles = await _fetch_from_yfinance(symbol, limit)
    if not articles:
        logger.warning("yfinance 수집 실패, RSS 시도: symbol=%s", symbol)
        articles = await _fetch_from_rss(symbol, limit)

    logger.info("뉴스 수집 완료: symbol=%s, count=%d", symbol, len(articles))
    return articles[:limit]


async def _fetch_from_yfinance(symbol: str, limit: int) -> list[RawArticle]:
    try:
        ticker = yf.Ticker(symbol)
        news_items = ticker.news or []
        articles = []
        for item in news_items[:limit]:
            content = item.get("content", {})
            title = item.get("title") or content.get("title", "")
            raw_text = (
                content.get("body", "")
                or content.get("summary", "")
                or title
            )
            pub_ts = item.get("providerPublishTime")
            pub_str = content.get("pubDate")
            if pub_ts:
                pub_dt = datetime.fromtimestamp(pub_ts, tz=timezone.utc)
            elif pub_str:
                pub_dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
            else:
                pub_dt = None
            url = (
                item.get("link")
                or item.get("url")
                or content.get("canonicalUrl", {}).get("url", "")
            )
            source = item.get("publisher") or content.get("provider", {}).get("displayName", "Yahoo Finance")
            articles.append(RawArticle(
                title=title,
                url=url,
                source=source,
                published_at=pub_dt,
                raw_content=raw_text,
            ))
        return articles
    except Exception as e:
        logger.error("yfinance 수집 오류: symbol=%s, error=%s", symbol, e)
        return []


async def _fetch_from_rss(symbol: str, limit: int) -> list[RawArticle]:
    articles = []
    keyword = symbol.upper()
    for source_name, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                title = entry.get("title", "")
                if keyword not in title.upper():
                    continue
                raw_content = entry.get("summary", "") or title
                pub = entry.get("published_parsed")
                pub_dt = (
                    datetime(*pub[:6], tzinfo=timezone.utc)
                    if pub else None
                )
                articles.append(RawArticle(
                    title=title,
                    url=entry.get("link", ""),
                    source=source_name,
                    published_at=pub_dt,
                    raw_content=raw_content,
                ))
        except Exception as e:
            logger.error("RSS 수집 오류: source=%s, error=%s", source_name, e)

    articles.sort(key=lambda a: a.published_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return articles[:limit]
