"""
research_config.py
───────────────────
심층 리서치 파이프라인 전용 설정.

파이프라인 코드(``generate.py`` 등)는 여전히 ``AppConfig`` 프로즌 dataclass를
참조한다 (원래 deep_research/app/config.py의 인터페이스를 그대로 유지).
값 자체는 backend의 통합 pydantic-settings(``app.config.get_settings``)에서
가져오는 어댑터 — 두 서비스가 하나의 ``.env``를 공유하도록 한다.

파이프라인 전용 모델 설정(``model_config.yaml``)은 backend의 뉴스용
model_config.yaml과 스키마가 다르므로(``defaults``/``sections`` vs
``features``/``defaults``) 별도 파일·로더를 유지한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.config import get_settings

PIPELINE_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = PIPELINE_DIR / "prompts"
ROOT_DIR = PIPELINE_DIR.parents[1]  # backend/


def _resolve_path(value: str, default_root: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = default_root / path
    return path


@lru_cache
def load_model_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or PIPELINE_DIR / "model_config.yaml"
    defaults: dict[str, Any] = {
        "defaults": {
            "section_model": "gemini-2.5-flash",
            "map_model": "gemini-2.5-flash-lite",
            "qa_model": "gemini-2.5-flash",
            "temperature": 0.2,
            "max_concurrency": 6,
        },
        "sections": {},
    }
    if not config_path.exists():
        return defaults
    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    merged = defaults | loaded
    merged["defaults"] = defaults["defaults"] | loaded.get("defaults", {})
    merged["sections"] = defaults["sections"] | loaded.get("sections", {})
    return merged


@dataclass(frozen=True)
class AppConfig:
    gemini_api_key: str | None
    edgar_user_agent: str
    cache_dir: Path
    output_dir: Path
    model_config: dict[str, Any]
    supabase_url: str | None
    supabase_service_role_key: str | None
    app_env: str
    debug: bool
    cors_origins: list[str]
    research_report_ttl_hours: int
    research_job_timeout_minutes: int
    api_use_llm: bool
    api_run_qa: bool


def load_config() -> AppConfig:
    settings = get_settings()
    return AppConfig(
        gemini_api_key=settings.gemini_api_key or None,
        edgar_user_agent=settings.edgar_user_agent,
        cache_dir=_resolve_path(settings.deep_research_cache_dir, ROOT_DIR),
        output_dir=_resolve_path(settings.deep_research_output_dir, ROOT_DIR),
        model_config=load_model_config(),
        supabase_url=settings.supabase_url,
        supabase_service_role_key=settings.supabase_service_role_key,
        app_env=settings.app_env,
        debug=settings.debug,
        cors_origins=settings.cors_origins,
        research_report_ttl_hours=settings.research_report_ttl_hours,
        research_job_timeout_minutes=settings.research_job_timeout_minutes,
        api_use_llm=settings.research_api_use_llm,
        api_run_qa=settings.research_api_run_qa,
    )
