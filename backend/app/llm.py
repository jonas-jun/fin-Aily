"""
llm.py
──────
Gemini 호출 공용 클라이언트. 뉴스 요약(summarization_service)과
심층 리서치 파이프라인(research_pipeline)이 함께 사용한다.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any


class LLMUnavailable(RuntimeError):
    pass


def parse_json_response(text: str) -> dict[str, Any]:
    """```json 코드펜스를 벗기고 JSON으로 파싱한다. 실패 시 첫 {...} 블록으로 재시도한다."""
    clean = text.strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?", "", clean).strip()
        clean = re.sub(r"```$", "", clean).strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", clean, re.S)
        if not match:
            raise
        return json.loads(match.group(0))


@dataclass
class GeminiClient:
    api_key: str | None

    async def generate_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, Any],
        temperature: float,
    ) -> dict[str, Any]:
        if not self.api_key:
            raise LLMUnavailable("GEMINI_API_KEY is not configured")
        try:
            from google import genai  # type: ignore
            from google.genai import types  # type: ignore
        except Exception as exc:
            raise LLMUnavailable("google-genai is not installed") from exc

        client = genai.Client(api_key=self.api_key)
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_schema=response_schema,
            temperature=temperature,
        )
        response = await client.aio.models.generate_content(
            model=model,
            contents=user_prompt,
            config=config,
        )
        text = getattr(response, "text", None)
        if not text and getattr(response, "candidates", None):
            parts = response.candidates[0].content.parts
            text = "".join(getattr(part, "text", "") for part in parts)
        if not text:
            raise RuntimeError("Gemini returned an empty response")
        return parse_json_response(text)

    async def generate_text(
        self,
        *,
        model: str,
        system_prompt: str | None = None,
        user_prompt: str,
        temperature: float = 0.2,
    ) -> str:
        if not self.api_key:
            raise LLMUnavailable("GEMINI_API_KEY is not configured")
        try:
            from google import genai  # type: ignore
            from google.genai import types  # type: ignore
        except Exception as exc:
            raise LLMUnavailable("google-genai is not installed") from exc

        client = genai.Client(api_key=self.api_key)
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
        )
        response = await client.aio.models.generate_content(
            model=model,
            contents=user_prompt,
            config=config,
        )
        return getattr(response, "text", "") or ""


async def gather_limited(limit: int, *coros: Any) -> list[Any]:
    semaphore = asyncio.Semaphore(limit)

    async def run(coro: Any) -> Any:
        async with semaphore:
            return await coro

    return await asyncio.gather(*(run(coro) for coro in coros))
