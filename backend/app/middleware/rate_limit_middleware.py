"""
rate_limit_middleware.py
────────────────────────
티커 검색 엔드포인트 Rate Limit 미들웨어.
인메모리 카운터(슬라이딩 윈도우) 사용.
프로덕션에서는 Redis로 교체 권장.
"""

import time
from collections import defaultdict, deque

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# 엔드포인트별 Rate Limit 설정: {path_prefix: (최대 횟수, 윈도우 초)}
RATE_LIMITS: dict[str, tuple[int, int]] = {
    "/v1/tickers/search": (30, 60),   # 30회/분
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        # {(ip, endpoint): deque[timestamp]}
        self._windows: dict[tuple, deque] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        limit_cfg = None
        for prefix, cfg in RATE_LIMITS.items():
            if path.startswith(prefix):
                limit_cfg = cfg
                break

        if limit_cfg is None:
            return await call_next(request)

        max_calls, window_sec = limit_cfg
        ip = request.client.host
        key = (ip, path)
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
