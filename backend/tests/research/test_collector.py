"""
test_collector.py
──────────────────
SEC EDGAR + Motley Fool 수집기 단위 테스트.
실제 네트워크 호출을 포함하므로 인터넷 연결이 필요합니다.
"""

import pytest
import pytest_asyncio

from app.services.research_collector import (
    EarningsCall,
    SecFiling,
    _parse_10k_sections,
    _period_to_fiscal,
    collect_all,
    collect_earnings_calls,
    collect_sec_filings,
)


# ── 유틸리티 단위 테스트 (네트워크 불필요) ────────────────────────────────────

class TestParseFiscalPeriod:
    def test_10k_annual(self):
        year, q = _period_to_fiscal("2024-12-31", "10-K")
        assert year == 2024
        assert q is None

    def test_10q_q1(self):
        year, q = _period_to_fiscal("2025-03-31", "10-Q")
        assert year == 2025
        assert q == 1

    def test_10q_q3(self):
        year, q = _period_to_fiscal("2025-09-30", "10-Q")
        assert year == 2025
        assert q == 3

    def test_invalid_date_fallback(self):
        year, q = _period_to_fiscal("bad-date", "10-Q")
        assert isinstance(year, int)


class TestParse10kSections:
    SAMPLE_TEXT = """
    ITEM 1. BUSINESS
    We are a semiconductor company.
    Revenue was $100M last year.

    ITEM 1A. RISK FACTORS
    Our main risks include competition and supply chain issues.

    ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS
    Revenue grew 20% YoY to $100M.
    Operating margin improved to 15%.

    ITEM 8. FINANCIAL STATEMENTS
    See consolidated balance sheets.
    """

    def test_extracts_item_1a(self):
        sections = _parse_10k_sections(self.SAMPLE_TEXT)
        assert "Item 1A" in sections
        assert "risk" in sections["Item 1A"].lower()

    def test_extracts_item_7(self):
        sections = _parse_10k_sections(self.SAMPLE_TEXT)
        assert "Item 7" in sections

    def test_no_crash_on_empty(self):
        sections = _parse_10k_sections("")
        assert isinstance(sections, dict)


# ── 실제 수집 통합 테스트 (네트워크 필요) ────────────────────────────────────

@pytest.mark.asyncio
class TestSecCollector:
    """SEC EDGAR 실수집 테스트 — 인터넷 연결 필요."""

    async def test_collect_ichr_filings(self):
        filings = await collect_sec_filings("ICHR", n=4)
        assert len(filings) >= 1
        for f in filings:
            assert f.form in ("10-K", "10-Q")
            assert f.fiscal_year > 2000
            assert isinstance(f.full_text, str)
            assert len(f.full_text) > 100

    async def test_collect_nvda_filings(self):
        filings = await collect_sec_filings("NVDA", n=2)
        assert len(filings) >= 1

    async def test_collect_aapl_filings(self):
        filings = await collect_sec_filings("AAPL", n=2)
        assert len(filings) >= 1

    async def test_10k_has_sections(self):
        filings = await collect_sec_filings("AAPL", n=4)
        ten_k_list = [f for f in filings if f.form == "10-K"]
        if ten_k_list:
            f = ten_k_list[0]
            # 섹션이 있으면 올바른 키를 가져야 함
            for key in f.sections:
                assert key.startswith("Item")


@pytest.mark.asyncio
class TestMotleyFoolCollector:
    """Motley Fool 수집 테스트 — 인터넷 연결 필요."""

    async def test_collect_nvda_calls(self):
        calls = await collect_earnings_calls("NVDA", n=4)
        # 스크래핑 결과는 0개일 수 있으나 예외는 발생하지 않아야 함
        assert isinstance(calls, list)
        for c in calls:
            assert isinstance(c, EarningsCall)
            assert c.fiscal_year > 2000
            assert c.fiscal_quarter in (1, 2, 3, 4)

    async def test_returns_empty_on_invalid_ticker(self):
        calls = await collect_earnings_calls("XYZNOTREAL123", n=2)
        assert isinstance(calls, list)


@pytest.mark.asyncio
class TestCollectAll:
    """통합 수집 테스트."""

    async def test_ichr_collect_all(self):
        filings, calls = await collect_all("ICHR", sec_n=2, call_n=4)
        # SEC 수집은 성공해야 함
        assert len(filings) >= 1

    async def test_aapl_collect_all(self):
        filings, calls = await collect_all("AAPL", sec_n=2, call_n=4)
        assert len(filings) >= 1
