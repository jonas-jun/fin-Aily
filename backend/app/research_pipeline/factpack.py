from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .edgar import EdgarBundle
from .financials import FinancialBundle
from .utils import bullet_list, format_money_b_from_raw, markdown_table


@dataclass
class FactPack:
    markdown: str
    tables: dict[str, str]
    data_gaps: list[str]


def build_factpack(edgar: EdgarBundle, financials: FinancialBundle) -> FactPack:
    profile = financials.company_profile
    identity = edgar.identity
    company_name = profile.get("company_name") or identity.company_name
    exchange = profile.get("exchange") or identity.exchange or "N/A"
    sector = profile.get("sector") or identity.sector or "N/A"
    market_cap = format_money_b_from_raw(profile.get("market_cap"))
    as_of = profile.get("as_of") or "N/A"

    financial_table = markdown_table(
        financials.financial_rows,
        [
            ("FY", "FY"),
            ("Revenue", "Revenue"),
            ("YoY", "YoY"),
            ("GPM", "GPM"),
            ("OPM", "OPM"),
            ("NPM", "NPM"),
            ("FCF", "FCF"),
            ("FCF Margin", "FCF Margin"),
            ("SBC / Revenue", "SBC / Revenue"),
            ("R&D / Revenue", "R&D / Revenue"),
            ("Capex / Revenue", "Capex / Revenue"),
            ("ROIC", "ROIC"),
            ("Shares", "Shares (M)"),
        ],
    )
    qoe_table = markdown_table(
        financials.qoe_rows,
        [
            ("FY", "FY"),
            ("Accrual Ratio", "Accrual Ratio"),
            ("FCF / Net Income", "FCF / Net Income"),
            ("Working Capital", "Working Capital"),
            ("SBC", "SBC"),
            ("D&A", "D&A"),
            ("Deferred Tax", "Deferred Tax"),
            ("ΔAR", "ΔAR"),
            ("ΔInventory", "ΔInventory"),
            ("ΔAP", "ΔAP"),
        ],
    )
    qoe_table += "\n\n※ ΔAR/ΔInventory/ΔAP는 현금흐름표 표기 기준(양수 = 해당 자산 증가/부채 감소로 인한 현금 유출)."
    capital_table = markdown_table(
        financials.capital_allocation_rows,
        [
            ("FY", "FY"),
            ("Buybacks", "Buybacks"),
            ("Dividends", "Dividends"),
            ("Acquisitions", "Acquisitions"),
            ("Debt Issued", "Debt Issued"),
            ("Debt Repaid", "Debt Repaid"),
            ("Shares", "Shares (M)"),
        ],
    )
    consensus_table = markdown_table(financials.consensus_rows, [("Metric", "Metric"), ("Value", "Value")])
    technical_table = markdown_table(financials.technical_rows, [("Metric", "Metric"), ("Value", "Value")])
    peer_table = markdown_table(financials.peer_rows, _peer_columns(financials.peer_rows))
    estimate_table = markdown_table(
        financials.estimate_rows,
        [
            ("Item", "Item"),
            ("Avg", "Avg"),
            ("Low", "Low"),
            ("High", "High"),
            ("Analysts", "Analysts"),
            ("YoY Growth", "YoY Growth"),
        ],
    )
    valuation_band_table = markdown_table(
        financials.valuation_band_rows,
        [
            ("Metric", "Metric"),
            ("Current", "Current"),
            ("5Y Min", "5Y Min"),
            ("5Y P25", "5Y P25"),
            ("5Y Median", "5Y Median"),
            ("5Y P75", "5Y P75"),
            ("5Y Max", "5Y Max"),
            ("Current Percentile", "Current Percentile"),
        ],
    )
    if financials.valuation_band_rows:
        valuation_band_table += (
            "\n\n※ 근사 계산: 일별 종가 ÷ 직전 공시 완료 회계연도 EPS(주당매출). "
            "회계연도 종료 후 90일 보고 지연을 가정한 trailing 밴드이며 forward 밴드가 아님."
        )

    gaps = [*edgar.errors, *financials.data_gaps]
    if not edgar.annual_filings:
        gaps.append("확인 불가: 최근 4개 연차 공시")

    markdown = "\n\n".join(
        [
            "### 회사 개요",
            (
                f"{identity.ticker} | {company_name} | {exchange} | {sector} | "
                f"시가총액 {market_cap} | 기준일 {as_of}"
            ),
            "### 5년 재무 시계열 (FY 기준)",
            financial_table,
            "### 밸류에이션·컨센서스",
            consensus_table,
            "### 데이터 한계",
            bullet_list(gaps) if gaps else "- 없음",
        ]
    )
    return FactPack(
        markdown=markdown,
        tables={
            "qoe_metrics": qoe_table,
            "capital_allocation_table": capital_table,
            "consensus_table": consensus_table,
            "estimate_table": estimate_table,
            "valuation_band_table": valuation_band_table,
            "technical_table": technical_table,
            "peer_table": peer_table,
        },
        data_gaps=gaps,
    )


def _peer_columns(rows: list[dict[str, Any]]) -> list[tuple[str, str]]:
    if not rows:
        return [("Peer", "Peer"), ("Note", "Note")]
    keys = list(rows[0].keys())
    return [(key, key) for key in keys]

