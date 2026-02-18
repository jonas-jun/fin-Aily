"""
main.py
───────
FastAPI 애플리케이션 진입점.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.middleware.rate_limit_middleware import RateLimitMiddleware
from app.routers import news_router, tickers_router, users_router

settings = get_settings()

app = FastAPI(
    title="Stock Insight API",
    description="AI 기반 글로벌 주식 뉴스 인사이트 플랫폼",
    version="1.0.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# ── 미들웨어 ──────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)

# ── 라우터 ────────────────────────────────────────────────────────────────────
PREFIX = "/v1"
app.include_router(tickers_router.router, prefix=PREFIX)
app.include_router(news_router.router,    prefix=PREFIX)
app.include_router(users_router.router,   prefix=PREFIX)

# ── 공통 에러 핸들러 ──────────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "서버 오류가 발생했습니다.", "status": 500}},
    )


@app.get("/health")
async def health_check():
    return {"status": "ok"}
