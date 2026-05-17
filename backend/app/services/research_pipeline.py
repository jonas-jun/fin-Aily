"""
research_pipeline.py
─────────────────────
계층적 Map-Reduce LLM 파이프라인.

Map-Pre → Map (분기별 병렬) → Reduce (종합 리포트 단일 호출)
"""

import asyncio
import logging
from typing import Optional

from google import genai
from google.genai import types

from app.config import get_feature_config
from app.services.research_collector import EarningsCall, SecFiling

logger = logging.getLogger(__name__)

# Map-Pre 적용 기준: 10-K 전체 텍스트가 이 길이 이상이면 섹션 압축 실행
_MAP_PRE_THRESHOLD_CHARS = 80_000


# ── 프롬프트 빌더 ──────────────────────────────────────────────────────────────

def _build_map_pre_prompt(ticker: str, section_name: str, section_text: str) -> str:
    return f"""당신은 SEC 공시 문서를 정밀하게 압축하는 금융 데이터 전문가입니다.

대상 티커: {ticker}
섹션: {section_name}

아래 텍스트에서 투자 판단에 필수적인 사실만 추출해 압축하세요.

## 지침
1. 구체적 수치, 금액, 비율은 절대 생략하지 말 것.
2. 고유명사(제품명, 고객사, 지역)는 원문 그대로 보존.
3. 반복·형식적 법률 문구는 제거.
4. 한국어로 작성. 수치·고유명사는 영문 병기 가능.
5. 출력은 마크다운 bullet 형식.

## 원문
{section_text}
"""


def _build_map_prompt(
    ticker: str,
    fiscal_label: str,
    filing_text: str,
    call_text: str,
) -> str:
    call_block = f"\n## 어닝스콜 스크립트\n{call_text}" if call_text.strip() else "\n## 어닝스콜 스크립트\n(해당 분기 스크립트 없음)"
    return f"""당신은 글로벌 상장 기업의 공시 문서와 컨퍼런스콜 스크립트에서
핵심 투자 단서를 추출하는 대용량 금융 데이터 정제 전문가입니다.

대상 티커: {ticker}
대상 분기: {fiscal_label}

## 추출 가이드라인
1. 구체적 수치(매출액·마진율·금액)와 고유 대명사(고객사·제품명)는 절대 누락/추상화 금지.
2. 가치 판단/추측은 배제, 원문 팩트와 경영진 워딩만 추출.
3. 해당 분기에 언급 없는 항목은 임의 생성 금지 — "해당 분기 언급 없음" 명시.
4. 한국어로 작성, 수치/고유명사/지표는 영문 병기.

## 출력 양식 (마크다운 6섹션 엄수)
### 1. 정량적 재무 실적 및 마진 (Financial Quality)
- 매출/영업이익/순이익 (YoY·QoQ 변화 포함)
- 매출총마진율(GPM), 영업마진율(OPM)
- 영업현금흐름(OCF), 잉여현금흐름(FCF)

### 2. 세그먼트 및 고객 집중도 (Segment & Customers)
- 사업부별/제품군별 매출 또는 비중
- 주요 고객사(Major Customers) 의존도 및 리스크 코멘트

### 3. 경영진 가이던스 및 핵심 가정 (Management Guidance)
- 다음 분기/연간 매출·EPS·마진율 전망
- 가이던스의 전제 가정(시장 환경, 수요 예측 등)

### 4. 자본 배분 및 투자 현황 (Capital Allocation)
- 자사주 매입, 배당, CapEx, M&A, 부채 상환

### 5. 공시 문구 및 리스크 팩터 변화 (Filing Delta)
- 이전 분기 대비 신규/강화된 리스크 요인
- 회계 정책 및 세그먼트 보고 방식 변화

### 6. 내러티브 및 핵심 키워드 (Narrative & Tone)
- 반복 강조 키워드/전략 방향 (AI 포지셔닝, 비용 절감 등)
- Q&A에서의 자신감 변화, 우선순위 변동

## 공시 문서
{filing_text}
{call_block}
"""


def _build_reduce_prompt(
    ticker: str,
    company_name: str,
    map_results: list[str],
) -> str:
    combined = "\n\n---\n\n".join(
        f"[분기 데이터 {i+1}]\n{r}" for i, r in enumerate(map_results)
    )
    return f"""당신은 미국 상장 기업 전문 기관투자자급 주식 리서치 애널리스트입니다.
제공된 [공시 문서(10-K/10-Q 요약)]와 [최근 컨퍼런스콜 요약]만을
바탕으로 외부 데이터 없이 1차 출처에 기반한 심층 투자 리포트를 한국어로 작성하라.

[기업명] {company_name} / [티커] {ticker}

## 데이터 원칙
1. 분석 근거는 오직 제공된 요약 데이터에 한정.
2. 수치는 제공 데이터에 명시된 검증 가능한 숫자만 인용.
3. 데이터에 없는 사항은 임의 추정 금지, "제공된 공시/컨콜 내 확인 불가" 명시.
4. 다음을 명확히 구분:
   - 확인된 과거 사실 (Historical Fact)
   - 경영진 가이던스 및 전망 (Management Guidance)
   - 분석가의 객관적 해석 (Analytical Interpretation)

## 보고서 구성
1. 투자 요약 (Investment Summary)
2. 사업 구조 및 세그먼트 분석
3. 재무 품질 및 마진 분석
4. 고객 및 매출 집중도 분석
5. 컨퍼런스콜 경영진 가이던스 분석
6. 핵심 리스크 (Risk Factors)
7. 공시 변화 분석 (Filing Delta)
8. 내러티브 변화 추적
9. 자본 배분 품질 분석 (Capital Allocation)
10. 최종 종합 평가

## 작성 지침
- 모든 섹션에서 단순 수치 나열이 아닌 '시간에 따른 변화(Trend)' 중심으로 분석.
- 수치 비교, 세그먼트 분석은 표(Table) 적극 활용.
- 출처를 명시 (예: "FY2025 10-Q 기준", "2024년 4분기 어닝스콜").
- 범용 산업 설명 배제, 이 기업 고유 데이터·인사이트에만 집중.
- 한국어 작성. 고유명사·지표명·수치는 영문 병기 가능.

## 분기별 데이터 (시간 순)
{combined}
"""


# ── LLM 호출 ──────────────────────────────────────────────────────────────────

async def _call_llm(
    client: genai.Client,
    model: str,
    prompt: str,
    max_tokens: int,
) -> str:
    """단일 LLM 호출. finish_reason=MAX_TOKENS 발생 시 경고 로깅."""
    config = types.GenerateContentConfig(max_output_tokens=max_tokens)
    response = await client.aio.models.generate_content(
        model=model,
        contents=prompt,
        config=config,
    )

    # finish_reason 모니터링
    try:
        finish_reason = response.candidates[0].finish_reason
        if str(finish_reason) in ("MAX_TOKENS", "2"):
            logger.warning(
                "MAX_TOKENS 도달: model=%s, max_tokens=%d — 모델 승격 검토 필요",
                model, max_tokens,
            )
    except Exception:
        pass

    return response.text or ""


# ── Map-Pre 단계 ───────────────────────────────────────────────────────────────

async def _run_map_pre(
    client: genai.Client,
    ticker: str,
    filing: SecFiling,
) -> str:
    """
    긴 10-K 섹션을 개별 압축 후 머지한다.
    10-Q 또는 짧은 10-K는 전체 텍스트를 그대로 반환.
    """
    cfg = get_feature_config("research_map_pre")

    if filing.form != "10-K" or len(filing.full_text) < _MAP_PRE_THRESHOLD_CHARS:
        return filing.full_text

    if not filing.sections:
        return filing.full_text[:_MAP_PRE_THRESHOLD_CHARS]

    # 핵심 섹션 우선순위
    priority = ["Item 1A", "Item 7", "Item 8", "Item 1", "Item 9A"]
    ordered_sections = sorted(
        filing.sections.items(),
        key=lambda x: priority.index(x[0]) if x[0] in priority else 99,
    )

    tasks = [
        _call_llm(client, cfg.model, _build_map_pre_prompt(ticker, name, text), cfg.max_tokens)
        for name, text in ordered_sections
        if text.strip()
    ]
    summaries = await asyncio.gather(*tasks, return_exceptions=True)

    merged_parts = []
    for (name, _), result in zip(ordered_sections, summaries):
        if isinstance(result, Exception):
            logger.warning("Map-Pre 섹션 실패: section=%s, error=%s", name, result)
            continue
        merged_parts.append(f"### {name} 요약\n{result}")

    return "\n\n".join(merged_parts)


# ── Map 단계 ──────────────────────────────────────────────────────────────────

async def _run_map(
    client: genai.Client,
    ticker: str,
    fiscal_label: str,
    filing_text: str,
    call_text: str,
) -> str:
    """단일 분기 마이크로 요약을 생성한다."""
    cfg = get_feature_config("research_map")
    prompt = _build_map_prompt(ticker, fiscal_label, filing_text, call_text)
    return await _call_llm(client, cfg.model, prompt, cfg.max_tokens)


# ── Reduce 단계 ───────────────────────────────────────────────────────────────

async def _run_reduce(
    client: genai.Client,
    ticker: str,
    company_name: str,
    map_results: list[str],
) -> str:
    """8개 분기 마이크로 요약을 결합해 최종 리포트를 생성한다."""
    cfg = get_feature_config("research_reduce")
    prompt = _build_reduce_prompt(ticker, company_name, map_results)
    return await _call_llm(client, cfg.model, prompt, cfg.max_tokens)


# ── 공개 엔트리포인트 ─────────────────────────────────────────────────────────

async def generate_report(
    ticker: str,
    company_name: str,
    filings: list[SecFiling],
    calls: list[EarningsCall],
    api_key: Optional[str] = None,
) -> tuple[str, str]:
    """
    SEC 공시 + 어닝스콜 → Map-Reduce → 최종 리포트 마크다운.
    반환값: (report_markdown, model_version)
    """
    client = genai.Client(api_key=api_key)

    # 분기 라벨 생성 함수
    def _fiscal_label(f: SecFiling) -> str:
        if f.form == "10-K":
            return f"FY{f.fiscal_year} 10-K"
        return f"FY{f.fiscal_year} Q{f.fiscal_quarter}"

    # 공시 ↔ 컨콜 매핑 (fiscal_year + quarter 기준)
    call_map: dict[tuple, str] = {}
    for c in calls:
        key = (c.fiscal_year, c.fiscal_quarter)
        call_map[key] = c.text

    # Map-Pre → Map 병렬 실행 (분기별)
    async def _process_filing(filing: SecFiling) -> str:
        label = _fiscal_label(filing)
        filing_text = await _run_map_pre(client, ticker, filing)
        call_text = call_map.get((filing.fiscal_year, filing.fiscal_quarter), "")
        try:
            return await _run_map(client, ticker, label, filing_text, call_text)
        except Exception as exc:
            logger.error("Map 실패: label=%s, error=%s", label, exc)
            raise

    if not filings and not calls:
        raise RuntimeError("ANALYSIS_FAILED: 수집된 공시 및 컨콜 데이터 없음")

    # 공시가 없으면 컨콜만으로 Map 실행 (최소 동작 보장)
    if not filings:
        logger.warning("공시 없음 — 컨콜 텍스트만으로 Map 단계 진행")
        cfg_map = get_feature_config("research_map")
        map_tasks = [
            _run_map(client, ticker, f"FY{c.fiscal_year} Q{c.fiscal_quarter}", "", c.text)
            for c in calls
        ]
    else:
        map_tasks = [_process_filing(f) for f in filings]

    map_results_raw = await asyncio.gather(*map_tasks, return_exceptions=True)

    map_results: list[str] = []
    for i, r in enumerate(map_results_raw):
        if isinstance(r, Exception):
            logger.error("Map 항목 실패 (건너뜀): index=%d, error=%s", i, r)
        else:
            map_results.append(r)

    if not map_results:
        raise RuntimeError("ANALYSIS_FAILED: 모든 Map 단계 실패")

    report_markdown = await _run_reduce(client, ticker, company_name, map_results)

    cfg_reduce = get_feature_config("research_reduce")
    return report_markdown, cfg_reduce.model
