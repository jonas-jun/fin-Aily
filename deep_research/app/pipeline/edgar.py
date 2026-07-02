from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any

from .utils import compact_whitespace, ensure_dir, read_json, trim_text, write_json


SEC_FILES_BASE = "https://www.sec.gov/files"
SEC_DATA_BASE = "https://data.sec.gov"
SEC_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"
ANNUAL_FORMS = {"10-K", "20-F"}


@dataclass
class CompanyIdentity:
    ticker: str
    cik: int | None
    company_name: str
    exchange: str | None = None
    sector: str | None = None


@dataclass
class FilingRecord:
    accession_no: str
    form_type: str
    filing_date: str
    report_date: str
    primary_document: str
    document_url: str
    event_items: str = ""
    items: dict[str, str] = field(default_factory=dict)
    text_excerpt: str = ""
    xbrl_tables: dict[str, str] = field(default_factory=dict)


@dataclass
class EdgarBundle:
    identity: CompanyIdentity
    annual_filings: list[FilingRecord]
    quarterly_filings: list[FilingRecord]
    earnings_releases: list[FilingRecord]
    sources: list[dict[str, str]]
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": asdict(self.identity),
            "annual_filings": [asdict(item) for item in self.annual_filings],
            "quarterly_filings": [asdict(item) for item in self.quarterly_filings],
            "earnings_releases": [asdict(item) for item in self.earnings_releases],
            "sources": self.sources,
            "errors": self.errors,
        }


class SecClient:
    def __init__(self, user_agent: str, cache_dir: Path, min_interval_seconds: float = 0.12):
        self.user_agent = user_agent
        self.cache_dir = ensure_dir(cache_dir)
        self.min_interval_seconds = min_interval_seconds
        self._last_request = 0.0

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / key

    def _is_fresh(self, path: Path, ttl_seconds: int | None) -> bool:
        if not path.exists():
            return False
        if ttl_seconds is None:
            return True
        age = time.time() - path.stat().st_mtime
        return age <= ttl_seconds

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.min_interval_seconds:
            time.sleep(self.min_interval_seconds - elapsed)
        self._last_request = time.monotonic()

    def _request_bytes(self, url: str) -> tuple[bytes, str]:
        self._throttle()
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json,text/html,text/plain,*/*",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read(), charset
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"SEC request failed {exc.code}: {url}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"SEC request failed: {url} ({exc.reason})") from exc

    def request_json(self, url: str, cache_key: str, ttl_seconds: int | None = 86400) -> dict[str, Any]:
        path = self._cache_path(cache_key)
        if self._is_fresh(path, ttl_seconds):
            return read_json(path)
        data, charset = self._request_bytes(url)
        payload = json.loads(data.decode(charset, errors="replace"))
        write_json(path, payload)
        return payload

    def request_text(self, url: str, cache_key: str, ttl_seconds: int | None = None) -> str:
        path = self._cache_path(cache_key)
        if self._is_fresh(path, ttl_seconds):
            return path.read_text(encoding="utf-8", errors="replace")
        data, charset = self._request_bytes(url)
        text = data.decode(charset, errors="replace")
        ensure_dir(path.parent)
        path.write_text(text, encoding="utf-8")
        return text

    def resolve_ticker(self, ticker: str) -> CompanyIdentity:
        ticker_upper = ticker.upper().strip()
        payload = self.request_json(
            f"{SEC_FILES_BASE}/company_tickers.json",
            "company_tickers.json",
            ttl_seconds=86400,
        )
        for value in payload.values():
            if str(value.get("ticker", "")).upper() == ticker_upper:
                return CompanyIdentity(
                    ticker=ticker_upper,
                    cik=int(value["cik_str"]),
                    company_name=str(value.get("title") or ticker_upper),
                )
        raise ValueError(f"Unable to resolve CIK for ticker: {ticker_upper}")

    def submissions(self, cik: int) -> dict[str, Any]:
        cik_padded = f"{cik:010d}"
        return self.request_json(
            f"{SEC_DATA_BASE}/submissions/CIK{cik_padded}.json",
            f"submissions/CIK{cik_padded}.json",
            ttl_seconds=3600,
        )

    def companyfacts(self, cik: int) -> dict[str, Any]:
        cik_padded = f"{cik:010d}"
        return self.request_json(
            f"{SEC_DATA_BASE}/api/xbrl/companyfacts/CIK{cik_padded}.json",
            f"companyfacts/CIK{cik_padded}.json",
            ttl_seconds=3600,
        )

    def list_filings(self, cik: int, forms: set[str], limit: int) -> list[FilingRecord]:
        payload = self.submissions(cik)
        recent = payload.get("filings", {}).get("recent", {})
        records: list[FilingRecord] = []
        form_values = recent.get("form", [])

        def column(name: str, idx: int) -> str:
            values = recent.get(name, [])
            return values[idx] if idx < len(values) and values[idx] else ""

        for idx, form_type in enumerate(form_values):
            if form_type not in forms:
                continue
            accession_no = column("accessionNumber", idx)
            primary_document = column("primaryDocument", idx)
            accession_path = accession_no.replace("-", "")
            url = f"{SEC_ARCHIVES_BASE}/{cik}/{accession_path}/{primary_document}"
            records.append(
                FilingRecord(
                    accession_no=accession_no,
                    form_type=form_type,
                    filing_date=column("filingDate", idx),
                    report_date=column("reportDate", idx),
                    primary_document=primary_document,
                    document_url=url,
                    event_items=column("items", idx),
                )
            )
        records.sort(key=lambda item: item.filing_date or item.report_date, reverse=True)
        return records[:limit]

    def list_earnings_releases(self, cik: int, limit: int) -> list[FilingRecord]:
        """실적 발표 8-K(Item 2.02)를 우선 수집하고, 부족하면 최신 8-K/6-K로 보충한다."""
        candidates = self.list_filings(cik, {"8-K", "6-K"}, limit * 6)
        earnings = [f for f in candidates if "2.02" in (f.event_items or "")]
        if len(earnings) < limit:
            seen = {f.accession_no for f in earnings}
            for filing in candidates:
                if len(earnings) >= limit:
                    break
                if filing.accession_no not in seen:
                    earnings.append(filing)
                    seen.add(filing.accession_no)
        earnings.sort(key=lambda item: item.filing_date or item.report_date, reverse=True)
        return earnings[:limit]

    def filing_index(self, cik: int, accession_no: str) -> list[str]:
        accession_path = accession_no.replace("-", "")
        try:
            payload = self.request_json(
                f"{SEC_ARCHIVES_BASE}/{cik}/{accession_path}/index.json",
                f"index/{cik}/{accession_path}.json",
                ttl_seconds=None,
            )
        except Exception:
            return []
        items = payload.get("directory", {}).get("item", [])
        return [str(entry.get("name", "")) for entry in items if entry.get("name")]

    def download_press_release_text(self, cik: int, filing: FilingRecord) -> str:
        """8-K의 EX-99 실적 보도자료 본문을 수집한다. 없으면 표지 문서로 폴백."""
        accession_path = filing.accession_no.replace("-", "")
        names = self.filing_index(cik, filing.accession_no)
        exhibit = _pick_ex99_document(names)
        texts: list[str] = []
        if exhibit:
            try:
                raw = self.request_text(
                    f"{SEC_ARCHIVES_BASE}/{cik}/{accession_path}/{exhibit}",
                    f"documents/{cik}/{accession_path}/{exhibit}.txt",
                    ttl_seconds=None,
                )
                texts.append(html_to_text(raw))
            except Exception:
                pass
        if not texts:
            texts.append(self.download_filing_text(cik, filing))
        return "\n\n".join(texts)

    def fetch_xbrl_report_tables(self, cik: int, filing: FilingRecord, categories: dict[str, Any]) -> dict[str, str]:
        """FilingSummary.xml의 R 리포트(XBRL 렌더링 테이블)에서 카테고리별 테이블을 추출한다."""
        accession_path = filing.accession_no.replace("-", "")
        try:
            summary_xml = self.request_text(
                f"{SEC_ARCHIVES_BASE}/{cik}/{accession_path}/FilingSummary.xml",
                f"documents/{cik}/{accession_path}/FilingSummary.xml",
                ttl_seconds=None,
            )
        except Exception:
            return {}
        reports = _parse_filing_summary(summary_xml)
        tables: dict[str, str] = {}
        for category, (pattern, max_reports) in categories.items():
            chunks: list[str] = []
            for short_name, html_file in reports:
                if len(chunks) >= max_reports:
                    break
                if not pattern.search(short_name):
                    continue
                try:
                    raw = self.request_text(
                        f"{SEC_ARCHIVES_BASE}/{cik}/{accession_path}/{html_file}",
                        f"documents/{cik}/{accession_path}/{html_file}.txt",
                        ttl_seconds=None,
                    )
                except Exception:
                    continue
                table_md = _r_report_to_markdown(raw)
                if table_md:
                    chunks.append(f"#### {short_name}\n\n{table_md}")
            if chunks:
                tables[category] = "\n\n".join(chunks)
        return tables

    def download_filing_text(self, cik: int, filing: FilingRecord) -> str:
        accession_path = filing.accession_no.replace("-", "")
        raw = self.request_text(
            filing.document_url,
            f"documents/{cik}/{accession_path}/{filing.primary_document}.txt",
            ttl_seconds=None,
        )
        return html_to_text(raw)

    def collect_company_bundle(self, ticker: str) -> EdgarBundle:
        errors: list[str] = []
        try:
            identity = self.resolve_ticker(ticker)
        except Exception as exc:
            fallback = CompanyIdentity(ticker=ticker.upper().strip(), cik=None, company_name=ticker.upper().strip())
            return EdgarBundle(fallback, [], [], [], [], [str(exc)])

        assert identity.cik is not None
        annuals = self.list_filings(identity.cik, ANNUAL_FORMS, 4)
        quarters = self.list_filings(identity.cik, {"10-Q"}, 4)
        eight_ks = self.list_earnings_releases(identity.cik, 8)

        for index, filing in enumerate(annuals):
            try:
                text = self.download_filing_text(identity.cik, filing)
                filing.items = extract_annual_items(text)
                filing.text_excerpt = trim_text(text, 30000)
            except Exception as exc:
                errors.append(f"{filing.form_type} {filing.accession_no} download failed: {exc}")
            try:
                categories = XBRL_REPORT_CATEGORIES if index < 2 else XBRL_REPORT_CATEGORIES_OLDER
                filing.xbrl_tables = self.fetch_xbrl_report_tables(identity.cik, filing, categories)
            except Exception as exc:
                errors.append(f"{filing.form_type} {filing.accession_no} XBRL report tables failed: {exc}")

        for filing in quarters:
            try:
                text = self.download_filing_text(identity.cik, filing)
                filing.items = extract_quarterly_items(text)
                filing.text_excerpt = trim_text(text, 20000)
            except Exception as exc:
                errors.append(f"{filing.form_type} {filing.accession_no} download failed: {exc}")

        for filing in eight_ks:
            try:
                text = self.download_press_release_text(identity.cik, filing)
                filing.text_excerpt = trim_text(text, 50000)
            except Exception as exc:
                errors.append(f"{filing.form_type} {filing.accession_no} download failed: {exc}")

        sources = []
        for filing in [*annuals, *quarters, *eight_ks]:
            sources.append(
                {
                    "form_type": filing.form_type,
                    "accession_no": filing.accession_no,
                    "filing_date": filing.filing_date,
                    "report_date": filing.report_date,
                    "url": filing.document_url,
                }
            )
        return EdgarBundle(identity, annuals, quarters, eight_ks, sources, errors)


# R 리포트 카테고리: (ShortName 매칭 패턴, 카테고리당 최대 리포트 수)
# 세그먼트/매출 분해는 최근 2개 연차 공시에서(각 공시가 3개년 수치 포함 → 4~5년 시계열 확보),
# 부채 상세는 오래된 공시에서는 수집하지 않는다.
XBRL_REPORT_CATEGORIES: dict[str, tuple[re.Pattern[str], int]] = {
    "segment": (re.compile(r"segment.*\(details?\)", re.I), 2),
    "revenue_disaggregation": (re.compile(r"(disaggregat|revenue.*net sales).*\(details?\)", re.I), 1),
    "debt": (re.compile(r"^debt\b.*\(details?\)", re.I), 2),
}
XBRL_REPORT_CATEGORIES_OLDER: dict[str, tuple[re.Pattern[str], int]] = {
    "segment": XBRL_REPORT_CATEGORIES["segment"],
}


def _pick_ex99_document(names: list[str]) -> str | None:
    htm_names = [name for name in names if name.lower().endswith((".htm", ".html"))]
    ex99 = [name for name in htm_names if re.search(r"ex[-_.]?99|99[-_.]?1|exh?99", name, re.I)]
    if not ex99:
        return None
    # EX-99.1(실적 보도자료)을 우선하고, 없으면 첫 번째 EX-99 계열 문서 사용
    for name in ex99:
        if re.search(r"99[-_.]?1|991", name, re.I):
            return name
    return ex99[0]


def _parse_filing_summary(xml_text: str) -> list[tuple[str, str]]:
    reports: list[tuple[str, str]] = []
    for block in re.findall(r"<Report\b.*?</Report>", xml_text, re.S | re.I):
        short_name = re.search(r"<ShortName>(.*?)</ShortName>", block, re.S | re.I)
        html_file = re.search(r"<HtmlFileName>(.*?)</HtmlFileName>", block, re.S | re.I)
        if short_name and html_file:
            reports.append((unescape(short_name.group(1).strip()), html_file.group(1).strip()))
    return reports


def _r_report_to_markdown(raw_html: str, max_rows: int = 40, max_cols: int = 10) -> str:
    try:
        from bs4 import BeautifulSoup  # type: ignore
    except Exception:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    table = soup.find("table")
    if table is None:
        return ""
    rows: list[list[str]] = []
    for tr in table.find_all("tr")[: max_rows + 4]:
        cells = [
            compact_whitespace(cell.get_text(" ", strip=True))
            for cell in tr.find_all(["th", "td"])[:max_cols]
        ]
        if any(cell for cell in cells):
            rows.append(cells)
    if len(rows) < 2:
        return ""
    width = max(len(row) for row in rows)
    normalized = [row + [""] * (width - len(row)) for row in rows[:max_rows]]
    header, *body = normalized
    lines = [
        "| " + " | ".join(cell or " " for cell in header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in body:
        lines.append("| " + " | ".join(cell.replace("|", "\\|") or " " for cell in row) + " |")
    return "\n".join(lines)


def html_to_text(raw: str) -> str:
    try:
        from bs4 import BeautifulSoup  # type: ignore

        soup = BeautifulSoup(raw, "html.parser")
        for tag in soup(["script", "style", "ix:header", "xbrli:context", "xbrli:unit"]):
            tag.decompose()
        text = soup.get_text("\n")
    except Exception:
        text = re.sub(r"<script.*?</script>", " ", raw, flags=re.I | re.S)
        text = re.sub(r"<style.*?</style>", " ", text, flags=re.I | re.S)
        text = re.sub(r"<[^>]+>", "\n", text)
    text = unescape(text)
    lines = [line.strip() for line in text.splitlines()]
    return compact_whitespace("\n".join(line for line in lines if line))


def _find_heading_positions(text: str, item_code: str) -> list[int]:
    escaped = re.escape(item_code).replace(r"\ ", r"\s*")
    pattern = re.compile(
        rf"(?im)(?:^|\n)\s*item\s+{escaped}\.?(?![A-Z0-9])\s*(?:[-:.\u2013\u2014]?\s*[A-Z][^\n]{{0,120}})?",
        re.I,
    )
    return [match.start() for match in pattern.finditer(text)]


def _choose_heading(text: str, item_code: str) -> int | None:
    positions = _find_heading_positions(text, item_code)
    if not positions:
        return None
    for pos in positions:
        if not _looks_like_table_of_contents(text, pos):
            return pos
    return positions[-1]


def _looks_like_table_of_contents(text: str, pos: int) -> bool:
    snippet = text[pos : pos + 1200]
    item_heading_count = len(re.findall(r"(?im)(?:^|\n)\s*item\s+\d+[A-Z]?\.", snippet))
    short_page_number_count = len(re.findall(r"(?m)^[0-9]{1,3}$", snippet))
    return item_heading_count >= 4 or short_page_number_count >= 4


def _extract_between_items(text: str, start_item: str, end_items: list[str], max_chars: int = 80000) -> str:
    start = _choose_heading(text, start_item)
    if start is None:
        return ""
    end_candidates = []
    for end_item in end_items:
        end_candidates.extend(pos for pos in _find_heading_positions(text[start + 20 :], end_item))
    end = min(end_candidates) + start + 20 if end_candidates else len(text)
    if end <= start:
        end = len(text)
    return trim_text(text[start:end], max_chars)


def extract_annual_items(text: str) -> dict[str, str]:
    return {
        "item1": _extract_between_items(text, "1", ["1A", "1B", "2"], 80000),
        "item1a": _extract_between_items(text, "1A", ["1B", "2", "3"], 80000),
        "item7": _extract_between_items(text, "7", ["7A", "8", "9"], 90000),
    }


def extract_quarterly_items(text: str) -> dict[str, str]:
    return {
        "part1_item2": _extract_between_items(text, "2", ["3", "4"], 50000),
        "part2_item1a": _extract_between_items(text, "1A", ["2", "3", "4", "5"], 40000),
    }


def fiscal_label(filing: FilingRecord) -> str:
    date_value = filing.report_date or filing.filing_date
    if not date_value:
        return filing.accession_no
    try:
        year = datetime.fromisoformat(date_value).year
    except ValueError:
        return date_value
    return f"FY{year}"
