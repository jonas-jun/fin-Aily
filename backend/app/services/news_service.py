"""
news_service.py
───────────────
뉴스 수집 서비스.
yfinance → RSS(Yahoo Finance) 순으로 수집을 시도하며,
시장 전체 뉴스를 위한 Yahoo Finance RSS 수집 기능을 제공한다.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import feedparser
import yfinance as yf
from newspaper import Article

from app.time_utils import utc_now

logger = logging.getLogger(__name__)

RSS_FEEDS = {
    "Yahoo_Finance": "https://finance.yahoo.com/rss/", # 야후 파이낸스 종합 금융 뉴스
}

@dataclass
class RawArticle:
    title: str
    url: str
    source: str
    published_at: Optional[datetime]
    raw_content: str

def _scrape_body(url: str) -> str:
    """기사 URL에서 본문을 추출한다. 실패 시 빈 문자열 반환."""
    if not url:
        return ""
    try:
        article = Article(url)
        article.download()
        article.parse()
        return article.text or ""
    except Exception as e:
        logger.debug("본문 스크래핑 실패: url=%s, error=%s", url, e)
        return ""


async def fetch_articles(symbol: str, limit: int = 10) -> list[RawArticle]:
    """티커 심볼에 대한 최신 뉴스를 수집한다."""
    articles = await _fetch_from_yfinance(symbol, limit)
    if not articles:
        logger.warning("yfinance 수집 실패, RSS 시도: symbol=%s", symbol)
        articles = await _fetch_from_rss(symbol, limit)

    logger.info("뉴스 수집 완료: symbol=%s, count=%d", symbol, len(articles))
    return articles[:limit]

async def fetch_market_news(limit: int = 10) -> list[RawArticle]:
    """Yahoo Finance 종합 금융 RSS에서 최신 시장 뉴스를 수집한다."""
    url = RSS_FEEDS["Yahoo_Finance"]

    articles = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:limit]:
            pub = entry.get("published_parsed")
            pub_dt = (
                datetime(*pub[:6], tzinfo=timezone.utc)
                if pub else utc_now()
            )
            articles.append(RawArticle(
                title=entry.get("title", ""),
                url=entry.get("link", ""),
                source="Yahoo Finance",
                published_at=pub_dt,
                raw_content=entry.get("summary", "") or _scrape_body(entry.get("link", "")) or entry.get("title", ""),
            ))
    except Exception as e:
        logger.error(f"{url} RSS 수집 오류: {e}")

    return articles

def _parse_pub_time(item: dict, content: dict) -> Optional[datetime]:
    """yfinance 0.2.x 뉴스 아이템에서 발행 시각을 추출한다."""
    # 1) 최상위 Unix 타임스탬프 (구형/신형 공통)
    pub_ts = item.get("providerPublishTime")
    if pub_ts:
        try:
            return datetime.fromtimestamp(int(pub_ts), tz=timezone.utc)
        except Exception:
            pass

    # 2) content.pubDate (ISO 문자열, yfinance 0.2.48+)
    pub_str = content.get("pubDate") or content.get("publishTime")
    if pub_str:
        try:
            return datetime.fromisoformat(str(pub_str).replace("Z", "+00:00"))
        except Exception:
            pass

    # 3) content.provider.publishTime (중첩 구조 대비)
    provider_ts = (content.get("provider") or {}).get("publishTime")
    if provider_ts:
        try:
            return datetime.fromtimestamp(int(provider_ts), tz=timezone.utc)
        except Exception:
            pass

    logger.debug("발행 시각 파싱 실패: item_keys=%s", list(item.keys()))
    return None


async def _fetch_from_yfinance(symbol: str, limit: int) -> list[RawArticle]:
    """yfinance를 통한 뉴스 수집"""
    try:
        ticker = yf.Ticker(symbol)
        news_items = ticker.news or []
        articles = []
        for item in (news_items or []):
            if not isinstance(item, dict):
                continue
            content = item.get("content") or {}
            title = item.get("title") or content.get("title", "")
            if not title:
                continue
            # yfinance 0.2.48+: 원문 URL은 content.clickThroughUrl에 있음
            # 값이 None인 경우를 대비해 or {} 패턴 사용
            url = (
                (content.get("clickThroughUrl") or {}).get("url", "")
                or item.get("link", "")
                or (content.get("canonicalUrl") or {}).get("url", "")
                or item.get("url", "")
            )
            raw_text = content.get("body", "") or content.get("summary", "") or _scrape_body(url) or title
            pub_dt = _parse_pub_time(item, content)
            articles.append(RawArticle(
                title=title,
                url=url,
                source=item.get("publisher", "Yahoo Finance"),
                published_at=pub_dt,
                raw_content=raw_text,
            ))
        return articles
    except Exception as e:
        logger.error("yfinance 수집 오류: symbol=%s, error=%s", symbol, e)
        return []

async def _fetch_from_rss(symbol: str, limit: int) -> list[RawArticle]:
    """RSS 피드를 통한 티커별 뉴스 필터링 수집"""
    articles = []
    keyword = symbol.upper()
    for source_name, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                title = entry.get("title", "")
                if keyword not in title.upper():
                    continue
                pub = entry.get("published_parsed")
                pub_dt = datetime(*pub[:6], tzinfo=timezone.utc) if pub else None
                articles.append(RawArticle(
                    title=title,
                    url=entry.get("link", ""),
                    source=source_name,
                    published_at=pub_dt,
                    raw_content=entry.get("summary", "") or title,
                ))
        except Exception as e:
            logger.error("RSS 수집 오류: source=%s, error=%s", source_name, e)

    articles.sort(key=lambda a: a.published_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return articles[:limit]