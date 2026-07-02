from __future__ import annotations

import re
from typing import Any

from .sections import SECTION_SPECS
from .utils import bullet_list


def assemble_report(
    *,
    ticker: str,
    company_name: str,
    generated_at: str,
    factpack_md: str,
    sections: dict[int, dict[str, Any]],
    sources: list[dict[str, str]],
    qa_issues: list[dict[str, Any]] | None = None,
) -> str:
    lines: list[str] = [
        f"# {company_name}({ticker.upper()}) Deep Research",
        "",
        f"- 생성 시각: {generated_at}",
        "- 기준: SEC EDGAR, XBRL companyfacts, yfinance 사용 가능 데이터",
        "- 원칙: 확인 불가 항목은 각 섹션의 데이터 한계로 분리",
        "",
        "## 목차",
        "",
    ]
    for spec in SECTION_SPECS:
        lines.append(f"- [{spec.number}. {spec.title_ko}](#{_anchor(spec.number, spec.title_ko)})")

    lines.extend(["", "## 데이터 팩트팩", "", factpack_md, ""])

    for spec in SECTION_SPECS:
        payload = sections.get(spec.number, {})
        lines.extend(
            [
                "",
                f'<a id="{_anchor(spec.number, spec.title_ko)}"></a>',
                "",
                f"## {spec.number}. {spec.title_ko}",
                "",
                spec.renderer(payload) if payload else "> 섹션 데이터가 없습니다.",
            ]
        )

    if qa_issues is not None:
        lines.extend(["", "## QA 점검", ""])
        if qa_issues:
            for issue in qa_issues:
                lines.append(
                    f"- {issue.get('type', 'Issue')} / {issue.get('location', 'N/A')}: "
                    f"{issue.get('description', '')}"
                )
        else:
            lines.append("- 자동 QA에서 문제를 찾지 못함")

    lines.extend(["", "## 출처", ""])
    if sources:
        for source in sources:
            label = " ".join(
                part
                for part in [
                    source.get("form_type", ""),
                    source.get("report_date", ""),
                    source.get("accession_no", ""),
                ]
                if part
            )
            lines.append(f"- [{label}]({source.get('url', '')})")
    else:
        lines.append("- 출처를 수집하지 못함")

    all_gaps = []
    for payload in sections.values():
        all_gaps.extend(payload.get("data_gaps", []) if isinstance(payload, dict) else [])
    if all_gaps:
        lines.extend(["", "## 전체 데이터 한계", "", bullet_list(dict.fromkeys(all_gaps).keys())])

    return "\n".join(lines).strip() + "\n"


def _anchor(number: int, title: str) -> str:
    slug = re.sub(r"[^a-z0-9가-힣\s-]", "", title.lower())
    slug = re.sub(r"\s+", "-", slug).strip("-")
    return f"{number}-{slug}"
