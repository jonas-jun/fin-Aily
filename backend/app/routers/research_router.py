from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from supabase import AsyncClient

from app.dependencies import create_db_client, get_db
from app.research_pipeline.edgar import SecClient
from app.research_pipeline.generate import GenerateOptions, ResearchPipeline
from app.research_pipeline.research_config import AppConfig, load_config
from app.research_pipeline.utils import ensure_dir
from app.schemas.research import ErrorBody, LatestReportResponse, ResearchJobResponse
from app.services import research_cache_service, ticker_service


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/research", tags=["research"])


SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,19}$")


@router.post(
    "/{symbol}",
    response_model=ResearchJobResponse,
    summary="심층 리서치 잡 시작",
)
async def create_research_job(
    symbol: str,
    background_tasks: BackgroundTasks,
    force: bool = False,
    db: AsyncClient = Depends(get_db),
) -> ResearchJobResponse:
    normalized = _normalize_symbol(symbol)
    config = load_config()
    await _ensure_known_symbol(normalized, config)
    await research_cache_service.cleanup_stale_jobs(db, config.research_job_timeout_minutes)

    ticker = await ticker_service.ensure_ticker(db, normalized)
    if not force:
        cached = await research_cache_service.get_cached_report(
            db,
            ticker_id=ticker["id"],
            ttl_hours=config.research_report_ttl_hours,
        )
        if cached:
            return _job_response(cached, normalized, cached=True, include_report=True)

    active = await research_cache_service.get_active_job(db, ticker_id=ticker["id"])
    if active:
        return _job_response(active, normalized, cached=False, include_report=False)

    # 인증 미도입 상태: 일일 한도는 사용자 식별(requested_by)에 의존하므로 비활성화.
    # 재도입 절차는 이슈 #8 참조.
    job = await research_cache_service.create_job(db, ticker_id=ticker["id"])
    background_tasks.add_task(run_research_job, int(job["id"]), int(ticker["id"]), normalized)
    return _job_response(job, normalized, cached=False, include_report=False)


@router.get(
    "/{symbol}",
    response_model=LatestReportResponse,
    summary="최신 완료 리포트 조회",
)
async def get_latest_report(
    symbol: str,
    db: AsyncClient = Depends(get_db),
) -> LatestReportResponse:
    normalized = _normalize_symbol(symbol)
    config = load_config()
    ticker = await ticker_service.ensure_ticker(db, normalized)
    row = await research_cache_service.get_cached_report(
        db,
        ticker_id=ticker["id"],
        ttl_hours=config.research_report_ttl_hours,
    )
    if not row or not row.get("report_md"):
        raise HTTPException(
            status_code=404,
            detail=ErrorBody(
                code="REPORT_NOT_FOUND",
                message=f"No completed research report found for {normalized}.",
            ).model_dump(),
        )
    return LatestReportResponse(
        symbol=normalized,
        report=row["report_md"],
        sections=row.get("sections"),
        sources=row.get("sources"),
        model_version=row.get("model_version"),
        created_at=row.get("created_at"),
        completed_at=row.get("completed_at"),
    )


@router.get(
    "/jobs/{job_id}",
    response_model=ResearchJobResponse,
    summary="심층 리서치 잡 상태 조회",
)
async def get_research_job(
    job_id: int,
    db: AsyncClient = Depends(get_db),
) -> ResearchJobResponse:
    row = await research_cache_service.get_job(db, job_id)
    if not row:
        raise HTTPException(
            status_code=404,
            detail=ErrorBody(code="JOB_NOT_FOUND", message=f"Job {job_id} was not found.").model_dump(),
        )
    ticker = row.get("tickers") or {}
    symbol = ticker.get("symbol") or "UNKNOWN"
    return _job_response(row, symbol, cached=False, include_report=row.get("status") == "completed")


async def run_research_job(job_id: int, ticker_id: int, symbol: str) -> None:
    config = load_config()
    db: AsyncClient | None = None
    try:
        if not config.supabase_url or not config.supabase_service_role_key:
            raise RuntimeError("Supabase settings are not configured")
        db = await create_db_client()
        await research_cache_service.mark_job_running(db, job_id, "리포트 생성 중")

        api_output_dir = ensure_dir(config.output_dir / "api")
        output_path = api_output_dir / f"{symbol}_{job_id}.md"
        pipeline = ResearchPipeline(config)
        await pipeline.run(
            GenerateOptions(
                ticker=symbol,
                output_path=output_path,
                dump=True,
                use_llm=config.api_use_llm,
                run_qa=config.api_run_qa,
            )
        )

        await research_cache_service.update_progress(db, job_id, "산출물 저장 중")
        artifact_dir = _artifact_dir(output_path)
        await research_cache_service.complete_job_from_artifacts(
            db=db,
            job_id=job_id,
            ticker_id=ticker_id,
            report_path=output_path,
            artifact_dir=artifact_dir,
            config=config,
        )
    except Exception as exc:
        logger.exception("Research job failed: job_id=%s symbol=%s", job_id, symbol)
        if db is not None:
            await research_cache_service.fail_job(db, job_id, str(exc))


async def _ensure_known_symbol(symbol: str, config: AppConfig) -> None:
    """SEC EDGAR 티커 맵에 존재하는 심볼인지 사전 확인한다.

    SEC 조회 자체가 실패(네트워크 순단 등)하면 검증을 통과시켜 잡 생성을
    막지 않는다 — 최종 방어는 ResearchPipeline.run()의 cik None 체크가 맡는다.
    """
    sec = SecClient(config.edgar_user_agent, config.cache_dir / "sec")
    try:
        await asyncio.to_thread(sec.resolve_ticker, symbol)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorBody(
                code="UNKNOWN_SYMBOL",
                message=f"SEC EDGAR에서 찾을 수 없는 심볼입니다: {symbol}",
            ).model_dump(),
        ) from exc
    except Exception:
        logger.warning("SEC ticker lookup failed for %s; allowing job creation", symbol, exc_info=True)


def _normalize_symbol(symbol: str) -> str:
    normalized = symbol.upper().strip()
    if not SYMBOL_PATTERN.match(normalized):
        raise HTTPException(
            status_code=422,
            detail=ErrorBody(
                code="INVALID_SYMBOL",
                message="Symbol must be 1-20 characters: letters, digits, dot, or hyphen.",
            ).model_dump(),
        )
    return normalized


def _artifact_dir(output_path: Path) -> Path:
    return output_path.parent / f"{output_path.stem}_artifacts"


def _job_response(
    row: dict[str, Any],
    symbol: str,
    *,
    cached: bool,
    include_report: bool,
) -> ResearchJobResponse:
    return ResearchJobResponse(
        job_id=int(row["id"]),
        symbol=symbol,
        status=row.get("status", "unknown"),
        progress=row.get("progress"),
        cached=cached,
        report=row.get("report_md") if include_report else None,
        error=row.get("error_message"),
        created_at=row.get("created_at"),
        completed_at=row.get("completed_at"),
    )
