"""
research_collector.py
─────────────────────
SEC EDGAR 공시 문서(10-K/10-Q) 및 Motley Fool 어닝스콜 스크립트 수집기.
기존 서비스 파일 일체 수정 없이 독립 모듈로 동작한다.
"""

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# EDGAR 접근에 필요한 User-Agent (SEC 정책)
_EDGAR_IDENTITY = "fin-aily-us junhot08@gmail.com"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# DuckDuckGo HTML 검색으로 Motley Fool 트랜스크립트 URL 탐색
_DDG_SEARCH_URL = "https://html.duckduckgo.com/html/"
_FOOL_TRANSCRIPT_PREFIX = "/earnings/call-transcripts/"
_FOOL_BASE = "https://www.fool.com"

# 10-K 핵심 섹션 패턴 (regex)
_SECTION_PATTERNS: list[tuple[str, str]] = [
    ("Item 1",  r"(?i)item\s+1[\.\s]+business\b"),
    ("Item 1A", r"(?i)item\s+1a[\.\s]+risk\s+factor"),
    ("Item 7",  r"(?i)item\s+7[\.\s]+management.s\s+discussion"),
    ("Item 8",  r"(?i)item\s+8[\.\s]+financial\s+statement"),
    ("Item 9A", r"(?i)item\s+9a[\.\s]+controls"),
]

# 섹션 종료 마커 (다음 Item 헤딩이 나타나면 이전 섹션 종료)
_SECTION_END_PATTERN = re.compile(r"(?i)\bitem\s+\d+[a-z]?\b[\.\s]")

# 섹션 최대 길이 (너무 긴 섹션은 앞부분만 사용)
_MAX_SECTION_CHARS = 60_000
_MAX_FULL_TEXT_CHARS = 200_000


# ── 데이터 모델 ────────────────────────────────────────────────────────────────

@dataclass
class SecFiling:
    form: str                         # "10-K" or "10-Q"
    fiscal_year: int
    fiscal_quarter: Optional[int]     # None for 10-K (annual)
    filing_date: str                  # "YYYY-MM-DD"
    period_of_report: str             # "YYYY-MM-DD"
    doc_id: str                       # accession number
    full_text: str                    # 전체 원문 (정제)
    sections: dict[str, str] = field(default_factory=dict)  # Item별 섹션 (10-K only)


@dataclass
class EarningsCall:
    fiscal_year: int
    fiscal_quarter: int
    event_date: str                   # "YYYY-MM-DD" (추정)
    source: str = "Motley Fool"
    source_url: str = ""
    text: str = ""


# ── 유틸리티 ──────────────────────────────────────────────────────────────────

def _date_to_str(d) -> str:
    if isinstance(d, datetime):
        return d.strftime("%Y-%m-%d")
    if isinstance(d, date):
        return d.strftime("%Y-%m-%d")
    return str(d)[:10]


def _period_to_fiscal(period_str: str, form: str) -> tuple[int, Optional[int]]:
    """period_of_report(YYYY-MM-DD) → (fiscal_year, fiscal_quarter)."""
    try:
        dt = datetime.strptime(period_str[:10], "%Y-%m-%d")
    except ValueError:
        return datetime.now().year, None

    month = dt.month
    year = dt.year
    if form == "10-K":
        # 연간보고서: fiscal_year는 period 연도, quarter None
        return year, None
    # 분기: 캘린더 분기 기준
    q = (month - 1) // 3 + 1
    return year, q


def _parse_10k_sections(text: str) -> dict[str, str]:
    """10-K 전체 텍스트에서 Item별 섹션을 정규식으로 추출한다."""
    sections: dict[str, str] = {}
    positions: list[tuple[str, int]] = []

    for name, pattern in _SECTION_PATTERNS:
        for m in re.finditer(pattern, text):
            positions.append((name, m.start()))
            break  # 가장 먼저 등장하는 위치만

    # 위치 순서로 정렬
    positions.sort(key=lambda x: x[1])

    for i, (name, start) in enumerate(positions):
        end = positions[i + 1][1] if i + 1 < len(positions) else len(text)
        chunk = text[start:end][:_MAX_SECTION_CHARS]
        sections[name] = chunk

    return sections


def _retry_sync(fn, max_retries: int = 3, base_delay: float = 1.0):
    """지수 백오프로 동기 함수를 최대 max_retries회 재시도한다."""
    last_exc: Exception = RuntimeError("unknown")
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                time.sleep(base_delay * (2 ** attempt))
    raise last_exc


# ── SEC EDGAR 수집 ─────────────────────────────────────────────────────────────

def _extract_text_from_doc(doc) -> tuple[str, dict[str, str]]:
    """
    edgartools 5.x TenK/TenQ 객체에서 전체 텍스트와 섹션 dict를 추출한다.
    - TenK: doc.sections['part_i_item_1a'].text() 방식
    - 직접 속성(risk_factors, management_discussion 등)은 str 반환
    """
    sections: dict[str, str] = {}
    full_parts: list[str] = []

    form = getattr(doc, "form", "")

    if form == "10-K":
        # edgartools 5.x TenK: 직접 str 속성 우선
        str_attr_map = [
            ("business",              "Item 1"),
            ("risk_factors",          "Item 1A"),
            ("management_discussion", "Item 7"),
        ]
        for attr, key in str_attr_map:
            val = getattr(doc, attr, None)
            if isinstance(val, str) and val.strip():
                sections[key] = val[:_MAX_SECTION_CHARS]
                full_parts.append(val)

    # doc.sections 으로 나머지 섹션 보완
    sec_key_map = {
        "part_i_item_1":  "Item 1",
        "part_i_item_1a": "Item 1A",
        "part_ii_item_7": "Item 7",
        "part_ii_item_8": "Item 8",
        "part_ii_item_9a": "Item 9A",
    }
    try:
        doc_secs = doc.sections  # edgartools 5.x Sections 객체
        for sec_key, item_key in sec_key_map.items():
            if item_key in sections:  # 이미 채워진 경우 건너뜀
                continue
            sec_obj = doc_secs.get(sec_key)
            if sec_obj is None:
                continue
            try:
                text = sec_obj.text()
                if text and text.strip():
                    sections[item_key] = text[:_MAX_SECTION_CHARS]
                    full_parts.append(text)
            except Exception:
                pass

        # 전체 텍스트가 비어있으면 모든 섹션 연결
        if not full_parts:
            for key in doc_secs:
                try:
                    t = doc_secs[key].text()
                    if t:
                        full_parts.append(t)
                except Exception:
                    pass
    except Exception as exc:
        logger.debug("doc.sections 접근 실패: %s", exc)

    full_text = "\n\n".join(full_parts)

    # 섹션이 없으면 전체 텍스트에서 정규식 파싱 (최후 폴백)
    if not sections and full_text:
        sections = _parse_10k_sections(full_text)

    return full_text[:_MAX_FULL_TEXT_CHARS], sections


# 어닝스 릴리즈 6-K 최소 길이 — 이보다 짧은 6-K는 어닝스 릴리즈가 아닌 것으로 판단
_6K_EARNINGS_MIN_CHARS = 40_000

# 6-K 어닝스 릴리즈 텍스트에서 실제 분기 종료일을 추출하는 패턴
_6K_PERIOD_PATTERN = re.compile(
    r"(?:ended|ending|period)\s+(\w+ \d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)


def _extract_text_foreign(doc) -> str:
    """20-F/6-K 문서에서 본문 텍스트를 추출한다."""
    try:
        text = doc.text() if callable(getattr(doc, "text", None)) else str(doc)
        if not text or len(text) < 100:
            text = str(doc)
        return text[:_MAX_FULL_TEXT_CHARS]
    except Exception:
        return str(doc)[:_MAX_FULL_TEXT_CHARS]


def _extract_6k_period(text: str, fallback: str) -> str:
    """6-K 어닝스 릴리즈 본문에서 분기 종료일(YYYY-MM-DD)을 추출한다."""
    m = _6K_PERIOD_PATTERN.search(text[:2000])
    if not m:
        return fallback
    raw = m.group(1).strip().rstrip(",")
    for fmt in ("%B %d %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return fallback


def _collect_sec_sync(ticker: str, n: int) -> list[SecFiling]:
    """edgartools 5.x를 사용해 최근 n건의 공시를 수집한다 (동기).

    국내 상장사(10-K/10-Q) 우선 시도 후 결과가 없으면
    외국 기업(20-F/6-K)으로 폴백한다.
    """
    try:
        from edgar import Company, set_identity  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError("edgartools 패키지가 설치되지 않았습니다: pip install edgartools") from exc

    set_identity(_EDGAR_IDENTITY)
    company = Company(ticker.upper())

    form_sets = [["10-K", "10-Q"], ["20-F", "6-K"]]
    for forms in form_sets:
        filings_col = company.get_filings(form=forms)
        results: list[SecFiling] = []
        # 6-K 중복 방지: 같은 (fiscal_year, fiscal_quarter)는 가장 긴 것 1개만
        seen_quarters: set[tuple] = set()
        count = 0

        for filing in filings_col:
            if count >= n:
                break
            try:
                form = filing.form
                filing_date = _date_to_str(filing.filing_date)
                period = _date_to_str(filing.period_of_report)
                accession = getattr(filing, "accession_no", "") or ""

                doc = filing.obj()

                if form == "6-K":
                    full_text = _extract_text_foreign(doc)
                    # 어닝스 릴리즈가 아닌 짧은 6-K 제외
                    if len(full_text) < _6K_EARNINGS_MIN_CHARS:
                        continue
                    sections: dict[str, str] = {}
                    # 6-K period_of_report는 공시일과 같은 경우가 많으므로 본문에서 추출
                    real_period = _extract_6k_period(full_text, period)
                    fiscal_year, fiscal_quarter = _period_to_fiscal(real_period, "10-Q")
                    # 같은 분기 중복 수집 방지
                    q_key = (fiscal_year, fiscal_quarter)
                    if q_key in seen_quarters:
                        continue
                    seen_quarters.add(q_key)
                    period = real_period
                elif form == "20-F":
                    full_text = _extract_text_foreign(doc)
                    if not full_text or len(full_text) < 200:
                        full_text, _ = _extract_text_from_doc(doc)
                    sections = {}
                    fiscal_year, fiscal_quarter = _period_to_fiscal(period, "10-K")
                else:
                    full_text, sections = _extract_text_from_doc(doc)
                    fiscal_year, fiscal_quarter = _period_to_fiscal(period, form)

                results.append(SecFiling(
                    form=form,
                    fiscal_year=fiscal_year,
                    fiscal_quarter=fiscal_quarter,
                    filing_date=filing_date,
                    period_of_report=period,
                    doc_id=accession,
                    full_text=full_text,
                    sections=sections,
                ))
                count += 1
            except Exception as exc:
                logger.warning("SEC 공시 파싱 오류 (건너뜀): %s", exc)
                count += 1

        if results:
            return results

    logger.error(
        "SEC 공시 없음: ticker=%s — 10-K/10-Q/20-F/6-K 형식의 공시를 찾을 수 없습니다.", ticker
    )
    return []


async def collect_sec_filings(ticker: str, n: int = 4) -> list[SecFiling]:
    """SEC EDGAR에서 최근 n건의 10-K/10-Q를 비동기로 수집한다."""
    try:
        filings = await asyncio.to_thread(_collect_sec_sync, ticker, n)
        logger.info("SEC 수집 완료: ticker=%s, count=%d", ticker, len(filings))
        return filings
    except Exception as exc:
        logger.error("SEC 수집 실패: ticker=%s, error=%s", ticker, exc)
        raise RuntimeError("COLLECTOR_SEC_FAILED") from exc


# ── Motley Fool 어닝스콜 수집 ──────────────────────────────────────────────────

def _find_fool_transcript_urls_sync(ticker: str, n: int) -> list[str]:
    """DuckDuckGo 검색으로 Motley Fool 어닝스콜 스크립트 URL 목록을 반환한다 (동기)."""
    query = f"site:fool.com earnings call transcript {ticker}"
    params = {"q": query}

    def _fetch():
        return requests.get(
            _DDG_SEARCH_URL,
            params=params,
            headers=_HEADERS,
            timeout=15,
            allow_redirects=True,
        )

    try:
        resp = _retry_sync(_fetch)
        soup = BeautifulSoup(resp.text, "lxml")
    except Exception as exc:
        logger.warning("DuckDuckGo 검색 실패: %s", exc)
        return []

    urls: list[str] = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        href: str = a["href"]
        if "fool.com" not in href:
            continue
        # DDG 리다이렉트 URL에서 실제 URL 추출
        if "uddg=" in href:
            qs = parse_qs(urlparse(href).query)
            real = unquote(qs.get("uddg", [""])[0])
        else:
            real = href if href.startswith("http") else "https:" + href
        if _FOOL_TRANSCRIPT_PREFIX not in real:
            continue
        if real not in seen:
            seen.add(real)
            urls.append(real)
        if len(urls) >= n:
            break

    return urls


def _fetch_fool_transcript_sync(url: str) -> str:
    """단일 Motley Fool 어닝스콜 스크립트 페이지에서 본문 텍스트를 추출한다 (동기)."""
    def _fetch():
        return requests.get(url, headers=_HEADERS, timeout=20)

    resp = _retry_sync(_fetch)
    soup = BeautifulSoup(resp.text, "lxml")

    # 여러 가능한 본문 컨테이너 시도
    for selector in [
        "div.tailwind-article-body",
        "div.article-body",
        "div#article-body",
        "article",
    ]:
        container = soup.select_one(selector)
        if container:
            return container.get_text(separator="\n", strip=True)

    # fallback: <main> 태그
    main = soup.find("main")
    if main:
        return main.get_text(separator="\n", strip=True)

    return ""


def _infer_quarter_from_url(url: str) -> tuple[int, int, str]:
    """URL에서 fiscal_year, fiscal_quarter, event_date를 추출한다."""
    # 패턴 예: /earnings/call-transcripts/2025/02/05/nvidia-nvda-q4-2025-.../
    date_match = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", url)
    quarter_match = re.search(r"-q(\d)-(\d{4})-", url)

    if date_match:
        year = int(date_match.group(1))
        month = int(date_match.group(2))
        day = int(date_match.group(3))
        event_date = f"{year}-{month:02d}-{day:02d}"
    else:
        event_date = datetime.now().strftime("%Y-%m-%d")
        year = datetime.now().year
        month = datetime.now().month

    if quarter_match:
        fiscal_quarter = int(quarter_match.group(1))
        fiscal_year = int(quarter_match.group(2))
    else:
        fiscal_year = year
        fiscal_quarter = (month - 1) // 3 + 1

    return fiscal_year, fiscal_quarter, event_date


async def collect_earnings_calls(ticker: str, n: int = 4) -> list[EarningsCall]:
    """Motley Fool에서 최근 n개 분기 어닝스콜 스크립트를 비동기로 수집한다."""
    try:
        urls = await asyncio.to_thread(_find_fool_transcript_urls_sync, ticker, n)
    except Exception as exc:
        logger.error("Motley Fool URL 검색 실패: ticker=%s, error=%s", ticker, exc)
        raise RuntimeError("COLLECTOR_TRANSCRIPT_FAILED") from exc

    if not urls:
        logger.warning("Motley Fool 스크립트 URL 없음: ticker=%s", ticker)
        return []

    calls: list[EarningsCall] = []
    for url in urls[:n]:
        try:
            text = await asyncio.to_thread(_fetch_fool_transcript_sync, url)
            fiscal_year, fiscal_quarter, event_date = _infer_quarter_from_url(url)
            calls.append(EarningsCall(
                fiscal_year=fiscal_year,
                fiscal_quarter=fiscal_quarter,
                event_date=event_date,
                source_url=url,
                text=text,
            ))
        except Exception as exc:
            logger.warning("Motley Fool 스크립트 수집 실패 (건너뜀): url=%s, error=%s", url, exc)

    logger.info("Motley Fool 수집 완료: ticker=%s, count=%d", ticker, len(calls))
    return calls


# ── 통합 수집 엔트리포인트 ─────────────────────────────────────────────────────

async def collect_all(
    ticker: str,
    sec_n: int = 8,
    call_n: int = 4,
) -> tuple[list[SecFiling], list[EarningsCall]]:
    """SEC 공시와 어닝스콜 스크립트를 동시에 수집한다."""
    sec_task = asyncio.create_task(collect_sec_filings(ticker, sec_n))
    call_task = asyncio.create_task(collect_earnings_calls(ticker, call_n))

    filings: list[SecFiling] = []
    calls: list[EarningsCall] = []
    sec_error: Optional[Exception] = None
    call_error: Optional[Exception] = None

    try:
        filings = await sec_task
    except Exception as exc:
        sec_error = exc

    try:
        calls = await call_task
    except Exception as exc:
        call_error = exc

    # 양쪽 모두 실패한 경우만 에러
    if sec_error and call_error:
        raise RuntimeError("COLLECTOR_SEC_FAILED") from sec_error

    if sec_error:
        logger.error("SEC 수집 실패, 컨콜만으로 진행: %s", sec_error)
    if call_error:
        logger.warning("컨콜 수집 실패, SEC만으로 진행: %s", call_error)

    return filings, calls
