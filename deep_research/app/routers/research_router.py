from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from supabase import AsyncClient, acreate_client

from app.config import load_config
from app.dependencies import get_db
from app.pipeline.generate import GenerateOptions, ResearchPipeline
from app.pipeline.utils import ensure_dir
from app.services import cache_service


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/research", tags=["research"])


class ResearchJobResponse(BaseModel):
    job_id: int
    symbol: str
    status: str
    progress: str | None = None
    cached: bool = False
    report: str | None = None
    error: str | None = None
    created_at: str | None = None
    completed_at: str | None = None


class LatestReportResponse(BaseModel):
    symbol: str
    status: str = "completed"
    report: str
    sections: dict[str, Any] | None = None
    sources: list[dict[str, Any]] | None = None
    model_version: str | None = None
    created_at: str | None = None
    completed_at: str | None = None


class ErrorBody(BaseModel):
    code: str = Field(..., examples=["REPORT_NOT_FOUND"])
    message: str


SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,19}$")


@router.post(
    "/{symbol}",
    response_model=ResearchJobResponse,
    summary="심층 리서치 잡 시작",
)
async def create_research_job(
    symbol: str,
    background_tasks: BackgroundTasks,
    db: AsyncClient = Depends(get_db),
) -> ResearchJobResponse:
    normalized = _normalize_symbol(symbol)
    config = load_config()
    await cache_service.cleanup_stale_jobs(db, config.research_job_timeout_minutes)

    ticker = await cache_service.ensure_ticker(db, normalized)
    cached = await cache_service.get_cached_report(
        db,
        ticker_id=ticker["id"],
        ttl_hours=config.research_report_ttl_hours,
    )
    if cached:
        return _job_response(cached, normalized, cached=True, include_report=True)

    active = await cache_service.get_active_job(db, ticker_id=ticker["id"])
    if active:
        return _job_response(active, normalized, cached=False, include_report=False)

    job = await cache_service.create_job(db, ticker_id=ticker["id"])
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
    ticker = await cache_service.ensure_ticker(db, normalized)
    row = await cache_service.get_latest_completed_report(db, ticker_id=ticker["id"])
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
    row = await cache_service.get_job(db, job_id)
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
        db = await acreate_client(config.supabase_url, config.supabase_service_role_key)
        await cache_service.mark_job_running(db, job_id, "리포트 생성 중")

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

        await cache_service.update_progress(db, job_id, "산출물 저장 중")
        artifact_dir = _artifact_dir(output_path)
        await cache_service.complete_job_from_artifacts(
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
            await cache_service.fail_job(db, job_id, str(exc))


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

