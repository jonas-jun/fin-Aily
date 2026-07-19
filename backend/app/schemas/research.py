from typing import Any

from pydantic import BaseModel, Field


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
