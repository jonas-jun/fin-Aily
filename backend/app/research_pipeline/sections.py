from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .utils import bullet_list, markdown_table


Renderer = Callable[[dict[str, Any]], str]


@dataclass(frozen=True)
class SectionSpec:
    number: int
    title_ko: str
    prompt_file: str
    wave: int
    response_schema: dict[str, Any]
    renderer: Renderer


STR = {"type": "string"}
ARR_STR = {"type": "array", "items": STR}


def arr_obj(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": properties,
            "required": required or list(properties.keys()),
        },
    }


def obj(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or list(properties.keys()),
    }


def section_schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    base = {
        "key_takeaway": STR,
        "data_gaps": ARR_STR,
    }
    all_properties = base | properties
    return obj(all_properties, ["key_takeaway", *(required or properties.keys()), "data_gaps"])


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _paragraphs(items: Any) -> str:
    values = []
    for item in _list(items):
        if isinstance(item, dict):
            heading = _string(item.get("heading"))
            paragraphs = "\n\n".join(_string(part) for part in _list(item.get("paragraphs")) if _string(part))
            values.append(f"### {heading}\n\n{paragraphs}" if heading else paragraphs)
        else:
            values.append(_string(item))
    values = [item for item in values if item]
    return "\n\n".join(values) if values else "N/A"


def _table(items: Any, columns: list[tuple[str, str]]) -> str:
    rows = [item for item in _list(items) if isinstance(item, dict)]
    return markdown_table(rows, columns) if rows else "N/A"


def _key_takeaway(data: dict[str, Any]) -> str:
    takeaway = _string(data.get("key_takeaway")) or "N/A"
    return f"> 핵심 결론: {takeaway}"


def _data_gaps(data: dict[str, Any]) -> str:
    gaps = _list(data.get("data_gaps"))
    if not gaps:
        return ""
    return "\n\n### 데이터 한계\n\n" + bullet_list(gaps)


def _failure(data: dict[str, Any]) -> str:
    if not data.get("__error__"):
        return ""
    return f"\n\n> 생성 상태: {data['__error__']}"


def render_executive(data: dict[str, Any]) -> str:
    return "\n\n".join(
        [
            _failure(data).strip(),
            "### 사업 개요",
            _string(data.get("business_overview")) or "N/A",
            "### 투자 논거",
            bullet_list(_list(data.get("investment_case"))),
            "### 강세 요인",
            bullet_list(_list(data.get("bull_points"))),
            "### 약세/리스크 요인",
            bullet_list(_list(data.get("bear_points"))),
            "### 비즈니스 퀄리티와 핵심 논쟁",
            _string(data.get("quality_assessment")) or "N/A",
            _string(data.get("key_debate")) or "N/A",
            _data_gaps(data).strip(),
        ]
    ).strip()


def render_business_structure(data: dict[str, Any]) -> str:
    return "\n\n".join(
        [
            _key_takeaway(data),
            _failure(data).strip(),
            "### 세그먼트·지역 믹스 변화",
            _paragraphs(data.get("segment_shift_analysis")),
            "### 경영진 내러티브 변화",
            _table(
                data.get("narrative_shifts"),
                [
                    ("theme", "Theme"),
                    ("direction", "Direction"),
                    ("evidence", "Evidence"),
                    ("implication", "Implication"),
                ],
            ),
            "### 중요도 상승 세그먼트",
            _table(data.get("rising_segments"), [("segment", "Segment"), ("rationale", "Rationale")]),
            "### 구조적 약화 세그먼트",
            _table(data.get("weakening_segments"), [("segment", "Segment"), ("rationale", "Rationale")]),
            _data_gaps(data).strip(),
        ]
    ).strip()


def render_financial_quality(data: dict[str, Any]) -> str:
    return "\n\n".join(
        [
            _key_takeaway(data),
            _failure(data).strip(),
            "### 추세 분석",
            _paragraphs(data.get("trend_analysis")),
            "### 마진 확장 동인",
            bullet_list(_list(data.get("margin_drivers"))),
            "### 마진 압축 리스크",
            bullet_list(_list(data.get("margin_risks"))),
            "### 영업 레버리지 평가",
            _string(data.get("operating_leverage_assessment")) or "N/A",
            "### 지속가능성 판단",
            _table([data.get("sustainability_verdict")] if isinstance(data.get("sustainability_verdict"), dict) else [], [("classification", "Classification"), ("rationale", "Rationale")]),
            _data_gaps(data).strip(),
        ]
    ).strip()


def render_filing_delta(data: dict[str, Any]) -> str:
    return "\n\n".join(
        [
            _key_takeaway(data),
            _failure(data).strip(),
            "### 공시 변화",
            _table(
                data.get("filing_deltas"),
                [
                    ("change_type", "Change"),
                    ("description", "Description"),
                    ("year", "Year"),
                    ("significance", "Significance"),
                ],
            ),
            "### 이익의 질",
            _paragraphs(data.get("earnings_quality")),
            "### 주의 신호",
            bullet_list(_list(data.get("quality_flags"))),
            _data_gaps(data).strip(),
        ]
    ).strip()


def render_competitive(data: dict[str, Any]) -> str:
    return "\n\n".join(
        [
            _key_takeaway(data),
            _failure(data).strip(),
            "### 세그먼트별 경쟁 구도",
            _table(
                data.get("segment_competition"),
                [
                    ("segment", "Segment"),
                    ("competitors", "Competitors"),
                    ("position", "Position"),
                    ("advantages", "Advantages"),
                    ("disadvantages", "Disadvantages"),
                ],
            ),
            "### 피어 비교 해석",
            _paragraphs(data.get("peer_comparison_analysis")),
            "### 집중도 리스크",
            _table(data.get("concentration_risks"), [("risk", "Risk"), ("evidence", "Evidence")]),
            _data_gaps(data).strip(),
        ]
    ).strip()


def render_capital_allocation(data: dict[str, Any]) -> str:
    grade = data.get("allocation_grade") if isinstance(data.get("allocation_grade"), dict) else {}
    return "\n\n".join(
        [
            _key_takeaway(data),
            _failure(data).strip(),
            "### 자본 배분 분석",
            _paragraphs(data.get("allocation_analysis")),
            "### 종합 등급",
            _table([grade], [("grade", "Grade"), ("rationale", "Rationale")]) if grade else "N/A",
            _data_gaps(data).strip(),
        ]
    ).strip()


def render_guidance(data: dict[str, Any]) -> str:
    return "\n\n".join(
        [
            _key_takeaway(data),
            _failure(data).strip(),
            "### 가이던스 변화 궤적",
            _table(
                data.get("guidance_trajectory"),
                [("quarter", "Quarter"), ("action", "Action"), ("summary", "Summary")],
            ),
            "### 가이던스 신뢰도",
            _string(data.get("credibility_assessment")) or "N/A",
            "### 반복 강조 주제",
            bullet_list(_list(data.get("recurring_themes"))),
            "### 언급 회피 가능 영역",
            _table(data.get("avoided_topics"), [("topic", "Topic"), ("evidence", "Evidence")]),
            _data_gaps(data).strip(),
        ]
    ).strip()


def render_valuation(data: dict[str, Any]) -> str:
    return "\n\n".join(
        [
            _key_takeaway(data),
            _failure(data).strip(),
            "### 컨센서스 분석",
            _paragraphs(data.get("consensus_analysis")),
            "### 밸류에이션 분석",
            _paragraphs(data.get("valuation_analysis")),
            "### 시나리오 분석",
            _table(
                data.get("scenarios"),
                [
                    ("case", "Case"),
                    ("probability_pct", "Probability"),
                    ("assumptions", "Assumptions"),
                    ("implication", "Implication"),
                ],
            ),
            "### 현 주가 내재 가정",
            _string(data.get("embedded_expectations")) or "N/A",
            _data_gaps(data).strip(),
        ]
    ).strip()


def render_risks(data: dict[str, Any]) -> str:
    return "\n\n".join(
        [
            _key_takeaway(data),
            _failure(data).strip(),
            "### 기술적 분석",
            _paragraphs(data.get("technical_summary")),
            "### 단기 실행 리스크",
            _table(data.get("short_term_risks"), [("risk", "Risk"), ("rationale", "Rationale")]),
            "### 장기 구조적 리스크",
            _table(data.get("structural_risks"), [("risk", "Risk"), ("rationale", "Rationale")]),
            _data_gaps(data).strip(),
        ]
    ).strip()


def render_variant(data: dict[str, Any]) -> str:
    return "\n\n".join(
        [
            _key_takeaway(data),
            _failure(data).strip(),
            "### Variant Perception",
            _paragraphs(data.get("variant_perception")),
            "### 최종 평점",
            _table(data.get("ratings"), [("axis", "Axis"), ("score", "Score"), ("rationale", "Rationale")]),
            "### 분기별 모니터링 KPI",
            _table(data.get("monitoring_kpis"), [("kpi", "KPI"), ("why", "Why")]),
            "### Thesis Killer",
            bullet_list(_list(data.get("thesis_killers"))),
            _data_gaps(data).strip(),
        ]
    ).strip()


S1 = obj(
    {
        "business_overview": STR,
        "investment_case": ARR_STR,
        "bull_points": ARR_STR,
        "bear_points": ARR_STR,
        "quality_assessment": STR,
        "key_debate": STR,
        "data_gaps": ARR_STR,
    }
)

S2 = section_schema(
    {
        "segment_shift_analysis": ARR_STR,
        "narrative_shifts": arr_obj(
            {"theme": STR, "direction": STR, "evidence": STR, "implication": STR},
            ["theme", "direction", "evidence", "implication"],
        ),
        "rising_segments": arr_obj({"segment": STR, "rationale": STR}),
        "weakening_segments": arr_obj({"segment": STR, "rationale": STR}),
    }
)

S3 = section_schema(
    {
        "trend_analysis": arr_obj({"heading": STR, "paragraphs": ARR_STR}),
        "margin_drivers": ARR_STR,
        "margin_risks": ARR_STR,
        "operating_leverage_assessment": STR,
        "sustainability_verdict": obj({"classification": STR, "rationale": STR}),
    }
)

S4 = section_schema(
    {
        "filing_deltas": arr_obj(
            {"change_type": STR, "description": STR, "year": STR, "significance": STR},
            ["change_type", "description", "year", "significance"],
        ),
        "earnings_quality": arr_obj({"heading": STR, "paragraphs": ARR_STR}),
        "quality_flags": ARR_STR,
    }
)

S5 = section_schema(
    {
        "segment_competition": arr_obj(
            {"segment": STR, "competitors": ARR_STR, "position": STR, "advantages": ARR_STR, "disadvantages": ARR_STR},
            ["segment", "competitors", "position", "advantages", "disadvantages"],
        ),
        "peer_comparison_analysis": ARR_STR,
        "concentration_risks": arr_obj({"risk": STR, "evidence": STR}),
    }
)

S6 = section_schema(
    {
        "allocation_analysis": arr_obj({"heading": STR, "paragraphs": ARR_STR}),
        "allocation_grade": obj({"grade": STR, "rationale": STR}),
    }
)

S7 = section_schema(
    {
        "guidance_trajectory": arr_obj({"quarter": STR, "action": STR, "summary": STR}),
        "credibility_assessment": STR,
        "recurring_themes": ARR_STR,
        "avoided_topics": arr_obj({"topic": STR, "evidence": STR}),
    }
)

S8 = section_schema(
    {
        "consensus_analysis": ARR_STR,
        "valuation_analysis": arr_obj({"heading": STR, "paragraphs": ARR_STR}),
        "scenarios": arr_obj(
            {"case": STR, "probability_pct": {"type": "integer"}, "assumptions": ARR_STR, "implication": STR},
            ["case", "probability_pct", "assumptions", "implication"],
        ),
        "embedded_expectations": STR,
    }
)

S9 = section_schema(
    {
        "technical_summary": ARR_STR,
        "short_term_risks": arr_obj({"risk": STR, "rationale": STR}),
        "structural_risks": arr_obj({"risk": STR, "rationale": STR}),
    }
)

S10 = section_schema(
    {
        "variant_perception": ARR_STR,
        "ratings": arr_obj({"axis": STR, "score": {"type": "integer"}, "rationale": STR}),
        "monitoring_kpis": arr_obj({"kpi": STR, "why": STR}),
        "thesis_killers": ARR_STR,
    }
)

QA_SCHEMA = obj(
    {
        "issues": arr_obj(
            {"type": STR, "location": STR, "description": STR},
            ["type", "location", "description"],
        )
    }
)

GUIDANCE_EXTRACT_SCHEMA = obj(
    {
        "period_label": STR,
        "revenue_actual": STR,
        "eps_actual": STR,
        "guidance_items": arr_obj({"metric": STR, "period": STR, "stated": STR}),
    }
)


SECTION_SPECS: list[SectionSpec] = [
    SectionSpec(1, "Executive Summary", "p01_executive_summary.txt", 2, S1, render_executive),
    SectionSpec(
        2,
        "Business Structure & Narrative Shift",
        "p02_business_structure.txt",
        1,
        S2,
        render_business_structure,
    ),
    SectionSpec(3, "Financial Quality & Margin", "p03_financial_quality.txt", 1, S3, render_financial_quality),
    SectionSpec(
        4,
        "Filing Delta & Quality of Earnings",
        "p04_filing_delta.txt",
        1,
        S4,
        render_filing_delta,
    ),
    SectionSpec(
        5,
        "Competitive Landscape & Customer Concentration",
        "p05_competitive_landscape.txt",
        1,
        S5,
        render_competitive,
    ),
    SectionSpec(
        6,
        "Capital Allocation",
        "p06_capital_allocation.txt",
        1,
        S6,
        render_capital_allocation,
    ),
    SectionSpec(
        7,
        "Earnings Call & Guidance",
        "p07_earnings_guidance.txt",
        1,
        S7,
        render_guidance,
    ),
    SectionSpec(
        8,
        "Analyst Consensus & Valuation",
        "p08_consensus_valuation.txt",
        1,
        S8,
        render_valuation,
    ),
    SectionSpec(
        9,
        "Technical & Key Risks",
        "p09_technical_risks.txt",
        1,
        S9,
        render_risks,
    ),
    SectionSpec(
        10,
        "Variant Perception & Final Assessment",
        "p10_variant_final.txt",
        2,
        S10,
        render_variant,
    ),
]


def get_section(number: int) -> SectionSpec:
    for spec in SECTION_SPECS:
        if spec.number == number:
            return spec
    raise KeyError(f"Unknown section number: {number}")


def wave_sections(wave: int) -> list[SectionSpec]:
    return [spec for spec in SECTION_SPECS if spec.wave == wave]


def fallback_section(spec: SectionSpec, reason: str) -> dict[str, Any]:
    return {
        "__error__": reason,
        "key_takeaway": f"{spec.title_ko} 섹션은 자동 생성에 실패했다.",
        "data_gaps": [f"확인 불가: {reason}"],
    }
