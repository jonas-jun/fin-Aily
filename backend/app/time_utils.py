"""
time_utils.py
─────────────
UTC 시각 헬퍼. 뉴스/캐시 서비스와 심층 리서치 파이프라인이 공통으로 사용한다.
"""

from datetime import datetime, timezone


def utc_now() -> datetime:
    """microsecond를 0으로 고정한 현재 UTC 시각."""
    return datetime.now(timezone.utc).replace(microsecond=0)


def utc_now_iso() -> str:
    return utc_now().isoformat()
