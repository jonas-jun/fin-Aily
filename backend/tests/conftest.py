"""
conftest.py
────────────
테스트 실행 전 .env 파일을 자동 로드한다.
GEMINI_API_KEY, SUPABASE_URL 등 환경 변수가 설정돼야 E2E 테스트가 활성화된다.
"""

from pathlib import Path

import pytest
from dotenv import load_dotenv

# backend/.env 경로를 명시적으로 지정
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=False)


@pytest.fixture(autouse=True)
def disable_rate_limit_for_tests():
    """테스트 중 Rate Limit을 비활성화해 테스트 간 간섭을 방지한다."""
    from app.middleware import rate_limit_middleware

    original = dict(rate_limit_middleware.RATE_LIMITS)
    rate_limit_middleware.RATE_LIMITS.clear()
    yield
    rate_limit_middleware.RATE_LIMITS.clear()
    rate_limit_middleware.RATE_LIMITS.update(original)
