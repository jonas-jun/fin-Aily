"""
summarization_service.py
────────────────────────
티커 단위 종합 요약 서비스.

기사 N개를 한 번의 API 호출로 묶어 bullet 종합 요약을 생성한다.
provider: "claude" | "gemini"
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

import anthropic
import google.generativeai as genai
from pydantic import BaseModel

logger = logging.getLogger(__name__)

MAX_ARTICLES        = 10
MAX_CONTENT_CHARS   = 500       # 기사당 원문 트리밍 (10개 × 500자 = 5,000자)
MAX_SUMMARY_BULLETS = 10

CLAUDE_MODEL  = "claude-haiku-4-5-20251001"
GEMINI_MODEL  = "gemini-2.5-flash"


class ArticleInput(BaseModel):
    id: int
    title: str
    source: str
    content: str


class SummaryPoint(BaseModel):
    point: str      # 종합 요약 bullet 문장
    quote: str      # 근거 원문 구절


class DigestResult(BaseModel):
    summary: list[SummaryPoint]     # bullet 목록 (최대 10개)
    sentiment_score: float
    sentiment_label: str            # Positive | Neutral | Negative
    model_version: str
    article_ids: list[int]
    article_count: int
    created_at: datetime


def _build_prompt(
    symbol: str,
    company_name: str,
    articles: list[ArticleInput],
    lang: str = "ko",
) -> str:
    lang_instruction = (
        "한국어로 작성하세요." if lang == "ko" else "Please write in English."
    )
    articles_block = ""
    for i, article in enumerate(articles, start=1):
        trimmed = article.content[:MAX_CONTENT_CHARS]
        articles_block += (
            f"[기사 {i}]\n"
            f"제목: {article.title}\n"
            f"출처: {article.source}\n"
            f"내용: {trimmed}\n\n"
        )

    return f"""당신은 금융 뉴스 분석 전문가입니다.

아래는 {symbol}({company_name})에 관한 최신 뉴스 기사 {len(articles)}개입니다.

## 지시사항
1. 전체 기사를 종합하여 {symbol} 투자자에게 중요한 핵심 인사이트를 bullet point로 요약하세요.
2. 투자자 관점에서 중요한 순서로 나열하고, {MAX_SUMMARY_BULLETS}줄을 절대 넘지 마세요.
3. 여러 기사에서 반복되는 내용은 하나로 합쳐 중복을 제거하세요.
4. {symbol}과 직접 관련 없는 일반 시장 정보는 포함하지 마세요.
5. 전체 뉴스 흐름에 대한 Sentiment Score를 -1.0(매우 부정) ~ +1.0(매우 긍정)으로 산출하세요.
6. {lang_instruction}

## 응답 형식 (반드시 JSON만 출력, 다른 텍스트 없음)
{{
  "summary": [
    {{"point": "첫 번째 bullet 문장", "quote": "해당 bullet의 근거가 되는 원문 구절 (영어 그대로)"}},
    {{"point": "두 번째 bullet 문장", "quote": "해당 bullet의 근거가 되는 원문 구절 (영어 그대로)"}}
  ],
  "sentiment_score": 0.00,
  "sentiment_label": "Positive | Neutral | Negative"
}}

## 뉴스 기사 목록
{articles_block}"""


def _parse_llm_response(raw_text: str) -> dict:
    """LLM 응답에서 JSON을 파싱한다. ```json ... ``` 펜스를 제거한다."""
    raw_text = raw_text.strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.lower().startswith("json"):
            raw_text = raw_text[4:]
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as e:
        logger.error("LLM JSON 파싱 실패: %s\n원문: %s", e, raw_text)
        raise ValueError(f"LLM 응답 파싱 실패: {e}") from e


def _call_claude(prompt: str, api_key: Optional[str]) -> tuple[str, str]:
    """Claude API를 호출하고 (raw_text, model_version)을 반환한다."""
    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text, CLAUDE_MODEL


def _call_gemini(prompt: str, api_key: Optional[str]) -> tuple[str, str]:
    """Gemini API를 호출하고 (raw_text, model_version)을 반환한다."""
    if api_key:
        genai.configure(api_key=api_key)
    model = genai.GenerativeModel(GEMINI_MODEL)
    response = model.generate_content(prompt)
    return response.text, GEMINI_MODEL


async def summarize_articles(
    symbol: str,
    company_name: str,
    articles: list[ArticleInput],
    lang: str = "ko",
    api_key: Optional[str] = None,
    provider: str = "claude",
) -> DigestResult:
    """
    기사 목록을 한 번의 API 호출로 종합 요약한다.

    Args:
        provider: "claude" 또는 "gemini"

    Raises:
        ValueError: articles 비어있거나 LLM 응답 파싱 실패 시
        anthropic.APIError / google.api_core.exceptions: API 호출 실패 시
    """
    if not articles:
        raise ValueError("articles는 최소 1개 이상이어야 합니다.")

    target = articles[:MAX_ARTICLES]
    prompt = _build_prompt(symbol, company_name, target, lang)

    logger.info(
        "LLM 호출: symbol=%s, articles=%d, lang=%s, provider=%s",
        symbol, len(target), lang, provider,
    )

    if provider == "gemini":
        raw_text, model_version = _call_gemini(prompt, api_key)
    else:
        raw_text, model_version = _call_claude(prompt, api_key)

    parsed = _parse_llm_response(raw_text)

    raw_bullets: list[dict] = parsed.get("summary", [])[:MAX_SUMMARY_BULLETS]
    if not raw_bullets:
        raise ValueError("LLM이 빈 summary를 반환했습니다.")

    bullets = [
        SummaryPoint(point=b.get("point", ""), quote=b.get("quote", ""))
        for b in raw_bullets
        if isinstance(b, dict) and b.get("point")
    ]
    if not bullets:
        raise ValueError("LLM이 유효한 summary point를 반환하지 않았습니다.")

    score = max(-1.0, min(1.0, float(parsed.get("sentiment_score", 0.0))))
    label = parsed.get("sentiment_label", "Neutral")
    if label not in ("Positive", "Neutral", "Negative"):
        label = "Positive" if score >= 0.2 else ("Negative" if score <= -0.2 else "Neutral")

    return DigestResult(
        summary=bullets,
        sentiment_score=round(score, 2),
        sentiment_label=label,
        model_version=model_version,
        article_ids=[a.id for a in target],
        article_count=len(target),
        created_at=datetime.now(tz=timezone.utc),
    )
