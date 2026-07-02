from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import load_config
from app.routers import research_router


config = load_config()

app = FastAPI(
    title="Fin Aily Deep Research API",
    description="SEC EDGAR, XBRL, yfinance, and Gemini based deep research report generator.",
    version="0.2.0",
    docs_url="/docs" if config.debug else None,
    redoc_url="/redoc" if config.debug else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_origin_regex=r"https://fin-aily-.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(research_router.router, prefix="/v1")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "서버 오류가 발생했습니다.",
                "status": 500,
            }
        },
    )


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "env": config.app_env,
        "db_configured": bool(config.supabase_url and config.supabase_service_role_key),
    }

