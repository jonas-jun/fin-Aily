"""
test_router_integration.py
────────────────────────────
GET /v1/research/{symbol} 엔드포인트 통합 테스트.
httpx.AsyncClient로 종단 HTTP 호출을 검증한다.
실제 LLM 호출 테스트는 GEMINI_API_KEY + Supabase 환경 변수가 필요하다.
"""

import os
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.research_service import ResearchReport

# 라우터가 직접 import한 함수를 mock하는 경로 (where it's used, not where it's defined)
_MOCK_TARGET = "app.routers.research_router.get_or_generate_report"


# ── 캐시 히트 시뮬레이션 ──────────────────────────────────────────────────────

MOCK_REPORT = ResearchReport(
    symbol="ICHR",
    company_name="Ichor Holdings, Ltd.",
    generated_at="2026-05-17T00:00:00+00:00",
    model_version="gemini-3.1-flash-lite",
    report_markdown="# 심층 투자 리포트\n\n## 1. 투자 요약\n테스트 리포트입니다.",
    source_metadata={
        "ticker": "ICHR",
        "analysis_period": "최근 4개 분기 공시 & 최근 8개 분기 컨퍼런스콜",
        "sources": {"sec_filings": [], "earning_calls": []},
    },
)


@pytest.mark.asyncio
class TestResearchRouterCacheHit:
    """캐시 히트 경로 테스트 (외부 의존성 없음)."""

    async def test_cache_hit_returns_200(self):
        with patch(_MOCK_TARGET, new_callable=AsyncMock, return_value=MOCK_REPORT):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/v1/research/ICHR")

        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "ICHR"
        assert "report_markdown" in data
        assert "source_metadata" in data

    async def test_response_schema(self):
        with patch(_MOCK_TARGET, new_callable=AsyncMock, return_value=MOCK_REPORT):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/v1/research/ichr")  # lowercase도 동작해야 함

        assert resp.status_code == 200
        data = resp.json()
        required_keys = {"symbol", "company_name", "generated_at", "model_version", "report_markdown", "source_metadata"}
        assert required_keys.issubset(data.keys())

    async def test_force_refresh_query_param(self):
        with patch(_MOCK_TARGET, new_callable=AsyncMock, return_value=MOCK_REPORT) as mock_fn:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/v1/research/ICHR?force_refresh=true")

        assert resp.status_code == 200
        assert mock_fn.called
        # force_refresh는 세 번째 위치 인자로 전달됨 (db, symbol, force_refresh)
        call_args = mock_fn.call_args
        positional = call_args.args if call_args.args else []
        keyword = call_args.kwargs if call_args.kwargs else {}
        force_val = keyword.get("force_refresh") or (positional[2] if len(positional) > 2 else None)
        assert force_val is True


@pytest.mark.asyncio
class TestResearchRouterErrors:
    """에러 응답 테스트."""

    async def test_sec_failed_returns_503(self):
        with patch(
            _MOCK_TARGET,
            new_callable=AsyncMock,
            side_effect=RuntimeError("COLLECTOR_SEC_FAILED"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/v1/research/ICHR")

        assert resp.status_code == 503
        assert resp.json()["detail"]["code"] == "COLLECTOR_SEC_FAILED"

    async def test_analysis_failed_returns_503(self):
        with patch(
            _MOCK_TARGET,
            new_callable=AsyncMock,
            side_effect=RuntimeError("ANALYSIS_FAILED"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/v1/research/ICHR")

        assert resp.status_code == 503

    async def test_transcript_failed_returns_503(self):
        with patch(
            _MOCK_TARGET,
            new_callable=AsyncMock,
            side_effect=RuntimeError("COLLECTOR_TRANSCRIPT_FAILED"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/v1/research/ICHR")

        assert resp.status_code == 503
        assert resp.json()["detail"]["code"] == "COLLECTOR_TRANSCRIPT_FAILED"


# ── 실환경 종단 테스트 (API 키 + DB 필요) ────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("GEMINI_API_KEY") or not os.environ.get("SUPABASE_URL"),
    reason="GEMINI_API_KEY 또는 SUPABASE_URL 환경 변수 없음",
)
class TestResearchRouterE2E:
    async def test_ichr_full_flow(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/v1/research/ICHR", timeout=180)

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["report_markdown"]) > 500

    async def test_cache_hit_on_second_request(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # 1차 요청 (생성 또는 캐시 히트)
            resp1 = await client.get("/v1/research/ICHR", timeout=180)
            assert resp1.status_code == 200

            # 2차 요청 (반드시 캐시 히트, 빠르게 응답)
            resp2 = await client.get("/v1/research/ICHR", timeout=30)
            assert resp2.status_code == 200
            # 동일한 generated_at → 캐시 히트 확인
            assert resp1.json()["generated_at"] == resp2.json()["generated_at"]
