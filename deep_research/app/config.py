from __future__ import annotations

import os
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
APP_DIR = ROOT_DIR / "app"
PROMPTS_DIR = APP_DIR / "prompts"


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _resolve_path(value: str | None, default: Path) -> Path:
    if not value:
        return default
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path


def _fallback_yaml(path: Path) -> dict[str, Any]:
    """Parse the tiny YAML subset used by model_config.yaml if PyYAML is absent."""
    result: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, result)]
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        key, _, value = raw_line.strip().partition(":")
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if value.strip():
            scalar = value.strip().strip('"').strip("'")
            if scalar.replace(".", "", 1).isdigit():
                parent[key] = float(scalar) if "." in scalar else int(scalar)
            else:
                parent[key] = scalar
        else:
            parent[key] = {}
            stack.append((indent, parent[key]))
    return result


def load_model_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or ROOT_DIR / "app" / "model_config.yaml"
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
    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        loaded = _fallback_yaml(config_path)
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
    _load_dotenv(ROOT_DIR / ".env")
    cache_dir = _resolve_path(os.getenv("DEEP_RESEARCH_CACHE_DIR"), ROOT_DIR / ".cache")
    output_dir = _resolve_path(os.getenv("DEEP_RESEARCH_OUTPUT_DIR"), ROOT_DIR / "reports")
    user_agent = os.getenv(
        "EDGAR_USER_AGENT",
        "fin-aily-us deep-research contact@example.com",
    )
    return AppConfig(
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        edgar_user_agent=user_agent,
        cache_dir=cache_dir,
        output_dir=output_dir,
        model_config=load_model_config(),
        supabase_url=os.getenv("SUPABASE_URL"),
        supabase_service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
        app_env=os.getenv("APP_ENV", "development"),
        debug=_env_bool("DEBUG", default=False),
        cors_origins=_env_list(
            "CORS_ORIGINS",
            default=["http://localhost:3000", "http://localhost:8000"],
        ),
        research_report_ttl_hours=_env_int("RESEARCH_REPORT_TTL_HOURS", default=168),
        research_job_timeout_minutes=_env_int("RESEARCH_JOB_TIMEOUT_MINUTES", default=15),
        api_use_llm=_env_bool("RESEARCH_API_USE_LLM", default=True),
        api_run_qa=_env_bool("RESEARCH_API_RUN_QA", default=False),
    )


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_list(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    if not value:
        return default
    if value.startswith("["):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except json.JSONDecodeError:
            pass
    return [item.strip() for item in value.split(",") if item.strip()]
