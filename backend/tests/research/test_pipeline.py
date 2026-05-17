"""
test_pipeline.py
─────────────────
Map-Reduce 파이프라인 테스트.
더미 데이터로 LLM 호출 없이 구조를 검증하고,
실제 LLM 호출 테스트는 GEMINI_API_KEY가 설정된 환경에서만 실행한다.
"""

import os

import pytest

from app.services.research_collector import EarningsCall, SecFiling
from app.services.research_pipeline import (
    _build_map_pre_prompt,
    _build_map_prompt,
    _build_reduce_prompt,
    generate_report,
)


# ── 프롬프트 빌더 단위 테스트 ─────────────────────────────────────────────────

class TestPromptBuilders:
    def test_map_pre_prompt_contains_ticker(self):
        prompt = _build_map_pre_prompt("NVDA", "Item 1A", "some risk text")
        assert "NVDA" in prompt
        assert "Item 1A" in prompt

    def test_map_prompt_6sections(self):
        prompt = _build_map_prompt("AAPL", "FY2025 Q1", "filing text", "call text")
        # 6개 섹션 헤딩 포함 확인
        for section_num in range(1, 7):
            assert f"### {section_num}." in prompt

    def test_map_prompt_no_call_text(self):
        prompt = _build_map_prompt("AAPL", "FY2025 Q1", "filing text", "")
        assert "스크립트 없음" in prompt

    def test_reduce_prompt_10sections(self):
        map_results = ["분기 1 요약", "분기 2 요약"]
        prompt = _build_reduce_prompt("ICHR", "Ichor Holdings", map_results)
        # Reduce 프롬프트에 보고서 구성 10개 섹션 포함
        assert "투자 요약" in prompt
        assert "최종 종합 평가" in prompt
        assert "분기 1 요약" in prompt


# ── 더미 데이터 준비 ──────────────────────────────────────────────────────────

def _make_dummy_filing(form: str, year: int, quarter=None) -> SecFiling:
    return SecFiling(
        form=form,
        fiscal_year=year,
        fiscal_quarter=quarter,
        filing_date=f"{year}-01-01",
        period_of_report=f"{year}-12-31",
        doc_id="0001234567-25-000001",
        full_text=f"This is a dummy {form} filing for year {year}. Revenue was $100M.",
        sections={"Item 1A": "Main risk is competition.", "Item 7": "Revenue grew 10%."},
    )


def _make_dummy_call(year: int, quarter: int) -> EarningsCall:
    return EarningsCall(
        fiscal_year=year,
        fiscal_quarter=quarter,
        event_date=f"{year}-04-01",
        source_url=f"https://www.fool.com/earnings/call-transcripts/{year}/04/01/test/",
        text=f"CEO: Revenue for Q{quarter} was $100M. We guide Q{quarter+1} to $110M.",
    )


# ── LLM 통합 테스트 (API 키 필요) ────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("GEMINI_API_KEY"),
    reason="GEMINI_API_KEY 환경 변수가 없음",
)
class TestPipelineLLM:
    async def test_generate_report_dummy_data(self):
        filings = [_make_dummy_filing("10-Q", 2025, 1)]
        calls = [_make_dummy_call(2025, 1)]

        report_md, model_version = await generate_report(
            ticker="TEST",
            company_name="Test Corp",
            filings=filings,
            calls=calls,
            api_key=os.environ["GEMINI_API_KEY"],
        )

        assert isinstance(report_md, str)
        assert len(report_md) > 100
        assert isinstance(model_version, str)

    async def test_report_has_10_sections(self):
        filings = [_make_dummy_filing("10-Q", 2025, 2)]
        calls = [_make_dummy_call(2025, 2)]

        report_md, _ = await generate_report(
            ticker="TEST",
            company_name="Test Corp",
            filings=filings,
            calls=calls,
            api_key=os.environ["GEMINI_API_KEY"],
        )

        # Reduce 리포트에 주요 섹션 키워드 포함 확인
        assert "투자 요약" in report_md or "Investment Summary" in report_md

    async def test_generate_report_only_calls(self):
        """공시 없이 컨콜만 있는 경우 폴백 동작."""
        calls = [_make_dummy_call(2025, 1), _make_dummy_call(2025, 2)]

        report_md, _ = await generate_report(
            ticker="TEST",
            company_name="Test Corp",
            filings=[],
            calls=calls,
            api_key=os.environ["GEMINI_API_KEY"],
        )

        assert isinstance(report_md, str)
        assert len(report_md) > 50
