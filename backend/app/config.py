"""
config.py
─────────
환경 변수 기반 설정. python-dotenv로 .env 파일 로드.
기능별 AI 모델 설정은 model_config.yaml에서 관리.
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Gemini
    gemini_api_key: str = ""

    # Supabase
    supabase_url: str
    supabase_service_role_key: str

    # App
    app_env: str = "development"
    debug: bool = False
    cors_origins: list[str] = ["http://localhost:3000", "https://fin-aily.vercel.app"]

    # Deep Research (심층 리서치)
    edgar_user_agent: str = "fin-aily-us deep-research contact@example.com"
    deep_research_cache_dir: str = ".cache"
    deep_research_output_dir: str = "reports"
    research_report_ttl_hours: int = 168
    research_job_timeout_minutes: int = 15
    research_api_use_llm: bool = True
    research_api_run_qa: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()


# ── 기능별 모델 설정 (model_config.yaml) ─────────────────────────────────────

@dataclass
class FeatureModelConfig:
    model: str
    max_tokens: int


@lru_cache
def _load_model_config() -> dict:
    config_path = Path(__file__).parent / "model_config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def get_feature_config(feature: str) -> FeatureModelConfig:
    """feature 이름으로 모델 설정을 조회한다. 없으면 defaults fallback."""
    config = _load_model_config()
    feat = config.get("features", {}).get(feature, config.get("defaults", {}))
    return FeatureModelConfig(
        model=feat["model"],
        max_tokens=feat.get("max_tokens", 1024),
    )


@dataclass
class CacheConfig:
    article_ttl_hours: float
    summary_ttl_hours: float


def get_cache_config() -> CacheConfig:
    """캐시 TTL 설정을 조회한다."""
    config = _load_model_config()
    cache = config.get("cache", {})
    return CacheConfig(
        article_ttl_hours=cache.get("article_ttl_hours", 1.0),
        summary_ttl_hours=cache.get("summary_ttl_hours", 24.0),
    )
