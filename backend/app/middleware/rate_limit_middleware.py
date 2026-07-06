"""
rate_limit_middleware.py
────────────────────────
엔드포인트별 Rate Limit 미들웨어.
인메모리 카운터(슬라이딩 윈도우) 사용 — 단일 인스턴스 전제.
다중 인스턴스로 스케일아웃 시 Redis로 교체 권장.
"""

import time
from collections import defaultdict, deque

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# 엔드포인트별 Rate Limit 설정: {(method, path_prefix): (최대 횟수, 윈도우 초)}
# method "*"는 모든 메서드. 카운트 윈도우는 prefix 단위로 공유된다
# (예: POST /v1/research/AAPL과 /v1/research/MSFT는 같은 윈도우).
RATE_LIMITS: dict[tuple[str, str], tuple[int, int]] = {
    ("*", "/v1/tickers/search"): (30, 60),  # 30회/분
    ("POST", "/v1/research"): (5, 60),      # 잡 생성 5회/분 — LLM 비용 방어. GET(조회·폴링)은 미제한
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        # {(ip, method, path_prefix): deque[timestamp]}
        self._windows: dict[tuple, deque] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        limit_cfg = None
        matched_key = None
        for (method, prefix), cfg in RATE_LIMITS.items():
            if (method == "*" or method == request.method) and path.startswith(prefix):
                limit_cfg = cfg
                matched_key = (method, prefix)
                break

        if limit_cfg is None:
            return await call_next(request)

        max_calls, window_sec = limit_cfg
        ip = request.client.host
        key = (ip, *matched_key)
        now = time.time()
        window = self._windows[key]

        # 윈도우 밖 타임스탬프 제거
        while window and window[0] < now - window_sec:
            window.popleft()

        if len(window) >= max_calls:
            return Response(
                content='{"error":{"code":"RATE_LIMIT_EXCEEDED","message":"요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요.","status":429}}',
                status_code=429,
                media_type="application/json",
            )

        window.append(now)
        return await call_next(request)
