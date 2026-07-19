"""
summarization_service.py
────────────────────────
티커 단위 및 시장 전체 종합 요약 서비스.
사용자 커스텀 프롬프트를 반영하여 시장 뉴스를 요약한다.
"""

import logging
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from string import Template
from typing import Optional

from pydantic import BaseModel

from app.config import get_feature_config
from app.llm import GeminiClient, parse_json_response
from app.time_utils import utc_now

logger = logging.getLogger(__name__)

MAX_ARTICLES        = 10
MAX_CONTENT_CHARS   = 1024
MAX_SUMMARY_BULLETS = 10
PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"

class ArticleInput(BaseModel):
    id: int
    title: str
    source: str
    content: str

class SummaryPoint(BaseModel):
    point: str      # 종합 요약 bullet 문장
    quote: str = "" # 근거 원문 구절 (Market Pulse에서는 미사용)

class DigestResult(BaseModel):
    summary: list[SummaryPoint]
    sentiment_score: float
    sentiment_label: str
    model_version: str
    article_ids: list[int]
    article_count: int
    created_at: datetime


def _build_prompt(
    symbol: str,
    company_name: str,
    articles: list[ArticleInput],
    lang: str = "ko",
    feature: str = "ticker_brief",
) -> str:
    lang_instruction = "한국어로 작성하세요." if lang == "ko" else "Please write in English."
    
    articles_block = ""
    for i, article in enumerate(articles, start=1):
        trimmed = article.content[:MAX_CONTENT_CHARS]
        articles_block += f"[기사 {i}] 제목: {article.title}\n출처: {article.source}\n내용: {trimmed}\n\n"

    template_name = "market_pulse.txt" if feature == "market_pulse" else "ticker_brief.txt"
    return _prompt_template(template_name).substitute(
        article_count=len(articles),
        articles_block=articles_block,
        company_name=company_name,
        lang_instruction=lang_instruction,
        max_summary_bullets=MAX_SUMMARY_BULLETS,
        symbol=symbol,
    )


@lru_cache
def _prompt_template(filename: str) -> Template:
    text = (PROMPTS_DIR / filename).read_text(encoding="utf-8").rstrip("\n")
    return Template(text)

async def summarize_articles(
    symbol: str,
    company_name: str,
    articles: list[ArticleInput],
    lang: str = "ko",
    api_key: Optional[str] = None,
    feature: str = "ticker_brief",
) -> DigestResult:
    if not articles:
        raise ValueError("기사가 없습니다.")

    feat_config = get_feature_config(feature)
    prompt = _build_prompt(symbol, company_name, articles[:MAX_ARTICLES], lang, feature)

    client = GeminiClient(api_key=api_key)
    raw_text = await client.generate_text(
        model=feat_config.model,
        user_prompt=prompt,
        max_tokens=feat_config.max_tokens,
    )
    model_version = feat_config.model

    try:
        parsed = parse_json_response(raw_text)
    except Exception:
        raise ValueError("LLM 응답 파싱 실패")
    bullets = [SummaryPoint(**b) for b in parsed.get("summary", [])]

    return DigestResult(
        summary=bullets,
        sentiment_score=parsed.get("sentiment_score", 0.0),
        sentiment_label=parsed.get("sentiment_label", "Neutral"),
        model_version=model_version,
        article_ids=[a.id for a in articles[:MAX_ARTICLES]],
        article_count=len(articles[:MAX_ARTICLES]),
        created_at=utc_now(),
    )
