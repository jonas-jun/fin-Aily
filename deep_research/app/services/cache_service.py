from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from supabase import AsyncClient

from app.config import AppConfig
from app.pipeline.utils import read_json

logger = logging.getLogger(__name__)


ACTIVE_STATUSES = ["pending", "running"]


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc).replace(microsecond=0)


async def ensure_ticker(db: AsyncClient, symbol: str) -> dict[str, Any]:
    normalized = symbol.upper().strip()
    existing = (
        await db.table("tickers")
        .select("*")
        .eq("symbol", normalized)
        .limit(1)
        .execute()
    )
    if existing.data:
        return existing.data[0]

    profile = await asyncio.to_thread(_lookup_ticker_profile, normalized)
    payload = {
        "symbol": normalized,
        "name": profile.get("name") or normalized,
        "exchange": profile.get("exchange"),
        "sector": profile.get("sector"),
    }
    try:
        inserted = await db.table("tickers").insert(payload).execute()
        if inserted.data:
            return inserted.data[0]
    except Exception:
        logger.info("Ticker insert raced or failed; retrying select: %s", normalized)

    retry = (
        await db.table("tickers")
        .select("*")
        .eq("symbol", normalized)
        .limit(1)
        .execute()
    )
    if retry.data:
        return retry.data[0]
    raise RuntimeError(f"Unable to create ticker row for {normalized}")


def _lookup_ticker_profile(symbol: str) -> dict[str, Any]:
    try:
        import yfinance as yf  # type: ignore

        info = yf.Ticker(symbol).info or {}
        return {
            "name": info.get("longName") or info.get("shortName"),
            "exchange": info.get("exchange"),
            "sector": info.get("sector"),
        }
    except Exception:
        return {"name": symbol, "exchange": None, "sector": None}


async def cleanup_stale_jobs(db: AsyncClient, timeout_minutes: int) -> None:
    cutoff = utc_now() - timedelta(minutes=timeout_minutes)
    await (
        db.table("research_reports")
        .update(
            {
                "status": "failed",
                "progress": "타임아웃",
                "error_message": f"Job exceeded {timeout_minutes} minutes without completion.",
                "completed_at": utc_now().isoformat(),
            }
        )
        .in_("status", ACTIVE_STATUSES)
        .lt("started_at", cutoff.isoformat())
        .execute()
    )
    await (
        db.table("research_reports")
        .update(
            {
                "status": "failed",
                "progress": "타임아웃",
                "error_message": f"Pending job exceeded {timeout_minutes} minutes without starting.",
                "completed_at": utc_now().isoformat(),
            }
        )
        .eq("status", "pending")
        .lt("created_at", cutoff.isoformat())
        .execute()
    )


async def get_cached_report(
    db: AsyncClient,
    ticker_id: int,
    ttl_hours: int,
    lang: str = "ko",
) -> dict[str, Any] | None:
    cutoff = utc_now() - timedelta(hours=ttl_hours)
    res = (
        await db.table("research_reports")
        .select("*")
        .eq("ticker_id", ticker_id)
        .eq("lang", lang)
        .eq("status", "completed")
        .gte("completed_at", cutoff.isoformat())
        .order("completed_at", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


async def get_latest_completed_report(
    db: AsyncClient,
    ticker_id: int,
    lang: str = "ko",
) -> dict[str, Any] | None:
    res = (
        await db.table("research_reports")
        .select("*")
        .eq("ticker_id", ticker_id)
        .eq("lang", lang)
        .eq("status", "completed")
        .order("completed_at", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


async def get_active_job(db: AsyncClient, ticker_id: int, lang: str = "ko") -> dict[str, Any] | None:
    res = (
        await db.table("research_reports")
        .select("*")
        .eq("ticker_id", ticker_id)
        .eq("lang", lang)
        .in_("status", ACTIVE_STATUSES)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


async def create_job(db: AsyncClient, ticker_id: int, lang: str = "ko") -> dict[str, Any]:
    payload = {
        "ticker_id": ticker_id,
        "status": "pending",
        "progress": "대기 중",
        "lang": lang,
        "created_at": utc_now().isoformat(),
    }
    res = await db.table("research_reports").insert(payload).execute()
    if not res.data:
        raise RuntimeError("Failed to create research job")
    return res.data[0]


async def get_job(db: AsyncClient, job_id: int) -> dict[str, Any] | None:
    res = (
        await db.table("research_reports")
        .select("*, tickers(symbol, name)")
        .eq("id", job_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


async def mark_job_running(db: AsyncClient, job_id: int, progress: str = "리포트 생성 중") -> None:
    await update_job(
        db,
        job_id,
        {
            "status": "running",
            "progress": progress,
            "started_at": utc_now().isoformat(),
        },
    )


async def update_progress(db: AsyncClient, job_id: int, progress: str) -> None:
    await update_job(db, job_id, {"progress": progress})


async def complete_job_from_artifacts(
    db: AsyncClient,
    job_id: int,
    ticker_id: int,
    report_path: Path,
    artifact_dir: Path,
    config: AppConfig,
) -> None:
    report_md = report_path.read_text(encoding="utf-8")
    sections = _load_sections(artifact_dir)
    edgar_inputs = _read_json_if_exists(artifact_dir / "edgar_inputs.json") or {}
    summaries = _read_json_if_exists(artifact_dir / "summaries.json") or {}
    sources = edgar_inputs.get("sources", [])
    await save_filing_cache(db, ticker_id, edgar_inputs, summaries)
    await update_job(
        db,
        job_id,
        {
            "status": "completed",
            "progress": "완료",
            "report_md": report_md,
            "sections": sections,
            "sources": sources,
            "model_version": _model_version(config),
            "error_message": None,
            "completed_at": utc_now().isoformat(),
        },
    )


async def fail_job(db: AsyncClient, job_id: int, error_message: str) -> None:
    await update_job(
        db,
        job_id,
        {
            "status": "failed",
            "progress": "실패",
            "error_message": error_message[:4000],
            "completed_at": utc_now().isoformat(),
        },
    )


async def update_job(db: AsyncClient, job_id: int, payload: dict[str, Any]) -> None:
    await db.table("research_reports").update(payload).eq("id", job_id).execute()


async def save_filing_cache(
    db: AsyncClient,
    ticker_id: int,
    edgar_inputs: dict[str, Any],
    summaries: dict[str, Any],
) -> None:
    by_accession = _summaries_by_accession(summaries)
    filings = [
        *edgar_inputs.get("annual_filings", []),
        *edgar_inputs.get("quarterly_filings", []),
        *edgar_inputs.get("earnings_releases", []),
    ]
    for filing in filings:
        accession_no = filing.get("accession_no")
        if not accession_no:
            continue
        payload = {
            "ticker_id": ticker_id,
            "accession_no": accession_no,
            "form_type": filing.get("form_type") or "N/A",
            "period_end": filing.get("report_date") or None,
            "section_texts": {
                "items": filing.get("items") or {},
                "text_excerpt": filing.get("text_excerpt") or "",
                "xbrl_tables": filing.get("xbrl_tables") or {},
            },
            "section_summaries": by_accession.get(accession_no, []),
        }
        try:
            await db.table("filings").upsert(payload, on_conflict="accession_no").execute()
        except Exception as exc:
            logger.warning("Failed to upsert filing cache %s: %s", accession_no, exc)


def _load_sections(artifact_dir: Path) -> dict[str, Any]:
    sections_dir = artifact_dir / "sections"
    if not sections_dir.exists():
        return {}
    sections: dict[str, Any] = {}
    for path in sorted(sections_dir.glob("*.json")):
        number = path.stem.split("_", 1)[0].lstrip("0") or "0"
        sections[number] = read_json(path)
    return sections


def _read_json_if_exists(path: Path) -> Any:
    if not path.exists():
        return None
    return read_json(path)


def _summaries_by_accession(summaries: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for items in summaries.values():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            accession_no = item.get("accession_no")
            if accession_no:
                result.setdefault(accession_no, []).append(item)
    return result


def _model_version(config: AppConfig) -> str:
    defaults = config.model_config.get("defaults", {})
    return json.dumps(
        {
            "section": defaults.get("section_model"),
            "map": defaults.get("map_model"),
            "qa": defaults.get("qa_model"),
        },
        ensure_ascii=False,
    )
