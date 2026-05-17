"""
research_router.py
───────────────────
심층 리서치 리포트 라우터.
GET /v1/research/{symbol} — 7일 캐시 기반 심층 AI 투자 리포트 조회/생성.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import get_db
from app.services.research_service import ResearchReport, get_or_generate_report

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/research", tags=["research"])


@router.get(
    "/{symbol}",
    response_model=ResearchReport,
    summary="종목 심층 AI 투자 리포트 (7일 캐시)",
)
async def get_research_report(
    symbol: str,
    force_refresh: bool = Query(default=False, description="true면 캐시 무효화 후 재생성"),
    db=Depends(get_db),
):
    """
    최근 8개 SEC 공시(10-K/10-Q, 약 2년치)와 최근 4개 분기 어닝스콜 스크립트를
    바탕으로 기관투자자급 심층 AI 리서치 리포트를 생성한다.
    7일 TTL 캐시를 사용하며, force_refresh=true 로 강제 갱신할 수 있다.
    리포트 생성은 60~120초 소요될 수 있다.
    """
    try:
        report = await get_or_generate_report(db, symbol, force_refresh)
        return report

    except RuntimeError as exc:
        code = str(exc).split(":")[0].strip()
        _error_map = {
            "COLLECTOR_SEC_FAILED":         (status.HTTP_503_SERVICE_UNAVAILABLE, "SEC EDGAR 공시 수집에 실패했습니다."),
            "COLLECTOR_TRANSCRIPT_FAILED":  (status.HTTP_503_SERVICE_UNAVAILABLE, "어닝스콜 스크립트 수집에 실패했습니다."),
            "ANALYSIS_FAILED":              (status.HTTP_503_SERVICE_UNAVAILABLE, "AI 분석 단계에서 오류가 발생했습니다."),
        }
        http_status, message = _error_map.get(code, (status.HTTP_503_SERVICE_UNAVAILABLE, "리포트 생성에 실패했습니다."))
        logger.error("리서치 리포트 오류: symbol=%s, code=%s, error=%s", symbol.upper(), code, exc)
        raise HTTPException(
            status_code=http_status,
            detail={"code": code, "message": message},
        )

    except Exception as exc:
        logger.error("리서치 리포트 예외: symbol=%s, error=%s", symbol.upper(), exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "ANALYSIS_FAILED", "message": "리포트 생성 중 오류가 발생했습니다."},
        )
