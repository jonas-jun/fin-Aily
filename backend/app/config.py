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
    # Anthropic
    anthropic_api_key: str = ""

    # Gemini
    gemini_api_key: str = ""

    # Supabase
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str

    # App
    app_env: str = "development"
    debug: bool = False
    cors_origins: list[str] = ["http://localhost:3000", "https://fin-aily.vercel.app"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()


# ── 기능별 모델 설정 (model_config.yaml) ─────────────────────────────────────

@dataclass
class FeatureModelConfig:
    provider: str
    model: str
    max_tokens: int


_model_config: dict | None = None


def _load_model_config() -> dict:
    global _model_config
    if _model_config is None:
        config_path = Path(__file__).parent / "model_config.yaml"
        with open(config_path) as f:
            _model_config = yaml.safe_load(f)
    return _model_config


def get_feature_config(feature: str) -> FeatureModelConfig:
    """feature 이름으로 모델 설정을 조회한다. 없으면 defaults fallback."""
    config = _load_model_config()
    feat = config.get("features", {}).get(feature, config.get("defaults", {}))
    return FeatureModelConfig(
        provider=feat["provider"],
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
