from __future__ import annotations

import warnings
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .edgar import CompanyIdentity
from .utils import format_money_b_from_raw, format_money_m, format_number, format_pct, format_x


ANNUAL_FORMS = {"10-K", "20-F", "40-F"}

DEFAULT_PEERS: dict[str, list[str]] = {
    "AAPL": ["MSFT", "GOOGL", "AMZN", "META", "NVDA"],
    "MSFT": ["AAPL", "GOOGL", "AMZN", "META", "ORCL"],
    "GOOGL": ["META", "MSFT", "AMZN", "AAPL", "NFLX"],
    "AMZN": ["MSFT", "GOOGL", "WMT", "META", "AAPL"],
    "META": ["GOOGL", "SNAP", "PINS", "MSFT", "AAPL"],
    "NVDA": ["AMD", "AVGO", "INTC", "QCOM", "TSM"],
    "TSLA": ["F", "GM", "TM", "RIVN", "LCID"],
}


@dataclass
class FinancialBundle:
    company_profile: dict[str, Any]
    financial_rows: list[dict[str, Any]]
    qoe_rows: list[dict[str, Any]]
    capital_allocation_rows: list[dict[str, Any]]
    consensus_rows: list[dict[str, Any]]
    estimate_rows: list[dict[str, Any]]
    valuation_band_rows: list[dict[str, Any]]
    technical_rows: list[dict[str, Any]]
    peer_rows: list[dict[str, Any]]
    data_gaps: list[str] = field(default_factory=list)


CONCEPT_TAGS: dict[str, list[str]] = {
    "revenue": [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
    ],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "pretax_income": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"],
    "tax_expense": ["IncomeTaxExpenseBenefit"],
    "cfo": ["NetCashProvidedByUsedInOperatingActivities"],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ],
    "sbc": [
        "ShareBasedCompensation",
        "ShareBasedCompensationArrangementByShareBasedPaymentAwardExpense",
    ],
    "rd": ["ResearchAndDevelopmentExpense"],
    "assets": ["Assets"],
    "current_assets": ["AssetsCurrent"],
    "liabilities": ["Liabilities"],
    "current_liabilities": ["LiabilitiesCurrent"],
    "equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    "debt_current": ["ShortTermBorrowings", "ShortTermDebtCurrent", "LongTermDebtCurrent"],
    "debt_long": ["LongTermDebtNoncurrent", "LongTermDebtAndFinanceLeaseObligationsNoncurrent"],
    "shares": ["EntityCommonStockSharesOutstanding", "WeightedAverageNumberOfDilutedSharesOutstanding"],
    "dna": ["DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet", "DepreciationAndAmortization"],
    "deferred_tax": ["DeferredIncomeTaxExpenseBenefit", "DeferredIncomeTaxesAndTaxCredits"],
    "ar_change": ["IncreaseDecreaseInAccountsReceivable", "IncreaseDecreaseInAccountsAndOtherReceivables"],
    "inventory_change": ["IncreaseDecreaseInInventories"],
    "ap_change": ["IncreaseDecreaseInAccountsPayable", "IncreaseDecreaseInAccountsPayableAndAccruedLiabilities"],
    "buybacks": ["PaymentsForRepurchaseOfCommonStock", "PaymentsForRepurchaseOfEquity"],
    "dividends": ["PaymentsOfDividends", "PaymentsOfDividendsCommonStock"],
    "acquisitions": ["PaymentsToAcquireBusinessesNetOfCashAcquired", "PaymentsToAcquireBusinessesAndInterestInAffiliates"],
    "debt_issued": ["ProceedsFromIssuanceOfLongTermDebt", "ProceedsFromBorrowings"],
    "debt_repaid": ["RepaymentsOfLongTermDebt", "RepaymentsOfDebt"],
}


def build_financial_bundle(
    ticker: str,
    identity: CompanyIdentity,
    companyfacts: dict[str, Any] | None,
) -> FinancialBundle:
    data_gaps: list[str] = []
    profile = {
        "ticker": ticker.upper(),
        "company_name": identity.company_name,
        "exchange": identity.exchange,
        "sector": identity.sector,
        "market_cap": None,
        "as_of": None,
    }

    series: dict[str, dict[int, dict[str, Any]]] = {}
    if companyfacts:
        for metric, tags in CONCEPT_TAGS.items():
            units = ["shares"] if metric == "shares" else ["USD", "USD/shares", "pure"]
            series[metric] = annual_series(companyfacts, tags, units)
    else:
        data_gaps.append("확인 불가: SEC companyfacts 데이터를 수집하지 못함")

    years = sorted({year for metric in ("revenue", "net_income", "cfo") for year in series.get(metric, {})})[-5:]
    if not years:
        data_gaps.append("확인 불가: 5년 XBRL 재무 시계열")

    financial_rows = _build_financial_rows(series, years, data_gaps)
    qoe_rows = _build_qoe_rows(series, years)
    capital_rows = _build_capital_rows(series, years)

    market_data = fetch_yfinance_market_data(ticker)
    profile |= market_data["profile"]
    data_gaps.extend(market_data["data_gaps"])

    consensus_rows = market_data["consensus_rows"]
    _append_fcf_yield(consensus_rows, series, years, profile.get("market_cap"))
    valuation_band_rows = _build_valuation_band_rows(series, years, market_data.get("price_history") or [])

    return FinancialBundle(
        company_profile=profile,
        financial_rows=financial_rows,
        qoe_rows=qoe_rows,
        capital_allocation_rows=capital_rows,
        consensus_rows=consensus_rows,
        estimate_rows=market_data["estimate_rows"],
        valuation_band_rows=valuation_band_rows,
        technical_rows=market_data["technical_rows"],
        peer_rows=market_data["peer_rows"],
        data_gaps=data_gaps,
    )


def _append_fcf_yield(
    consensus_rows: list[dict[str, Any]],
    series: dict[str, dict[int, dict[str, Any]]],
    years: list[int],
    market_cap: Any,
) -> None:
    if not years or not market_cap:
        return
    latest = years[-1]
    cfo = _value(series, "cfo", latest)
    capex_raw = _value(series, "capex", latest)
    if cfo is None or capex_raw is None:
        return
    fcf = cfo - abs(capex_raw)
    try:
        yield_pct = fcf / float(market_cap) * 100
    except (TypeError, ValueError, ZeroDivisionError):
        return
    consensus_rows.append(
        {"Metric": f"FCF Yield (FY{latest} FCF / 현재 시총)", "Value": format_pct(yield_pct)}
    )


def _taxonomy_items(companyfacts: dict[str, Any]) -> list[dict[str, Any]]:
    facts = companyfacts.get("facts", {})
    return [facts.get(name, {}) for name in ("us-gaap", "ifrs-full", "dei")]


def annual_series(
    companyfacts: dict[str, Any],
    tags: list[str],
    unit_candidates: list[str],
) -> dict[int, dict[str, Any]]:
    by_year: dict[int, dict[str, Any]] = {}
    for taxonomy in _taxonomy_items(companyfacts):
        for tag in tags:
            concept = taxonomy.get(tag)
            if not concept:
                continue
            units = concept.get("units", {})
            for unit in unit_candidates:
                if unit not in units:
                    continue
                for entry in units[unit]:
                    if entry.get("form") not in ANNUAL_FORMS:
                        continue
                    if entry.get("fp") not in (None, "FY") and not str(entry.get("frame", "")).startswith("CY"):
                        continue
                    year = _entry_year(entry)
                    if year is None or entry.get("val") is None:
                        continue
                    candidate = {
                        "value": float(entry["val"]),
                        "filed": entry.get("filed", ""),
                        "end": entry.get("end", ""),
                        "form": entry.get("form", ""),
                        "tag": tag,
                        "unit": unit,
                    }
                    existing = by_year.get(year)
                    if existing is None or candidate["filed"] >= existing.get("filed", ""):
                        by_year[year] = candidate
    return by_year


def _entry_year(entry: dict[str, Any]) -> int | None:
    if entry.get("fy"):
        try:
            return int(entry["fy"])
        except (TypeError, ValueError):
            pass
    end = entry.get("end")
    if end and len(end) >= 4:
        try:
            return int(str(end)[:4])
        except ValueError:
            return None
    return None


def _value(series: dict[str, dict[int, dict[str, Any]]], metric: str, year: int) -> float | None:
    item = series.get(metric, {}).get(year)
    if not item:
        return None
    return float(item["value"])


def _usd_m(value: float | None) -> float | None:
    return None if value is None else value / 1_000_000


def _shares_m(value: float | None) -> float | None:
    return None if value is None else value / 1_000_000


def _pct(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator * 100


def _build_financial_rows(
    series: dict[str, dict[int, dict[str, Any]]],
    years: list[int],
    data_gaps: list[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    previous_revenue: float | None = None
    previous_invested_capital: float | None = None

    for year in years:
        revenue = _value(series, "revenue", year)
        gross_profit = _value(series, "gross_profit", year)
        operating_income = _value(series, "operating_income", year)
        net_income = _value(series, "net_income", year)
        cfo = _value(series, "cfo", year)
        capex_raw = _value(series, "capex", year)
        capex = abs(capex_raw) if capex_raw is not None else None
        fcf = cfo - capex if cfo is not None and capex is not None else None
        sbc = _value(series, "sbc", year)
        rd = _value(series, "rd", year)
        shares = _value(series, "shares", year)

        invested_capital = _invested_capital(series, year)
        roic = _roic(series, year, operating_income, invested_capital, previous_invested_capital)
        previous_invested_capital = invested_capital if invested_capital is not None else previous_invested_capital

        revenue_yoy = None
        if revenue is not None and previous_revenue not in (None, 0):
            revenue_yoy = (revenue / previous_revenue - 1) * 100
        previous_revenue = revenue if revenue is not None else previous_revenue

        rows.append(
            {
                "FY": f"FY{year}",
                "Revenue": format_money_m(_usd_m(revenue)),
                "YoY": format_pct(revenue_yoy),
                "GPM": format_pct(_pct(gross_profit, revenue)),
                "OPM": format_pct(_pct(operating_income, revenue)),
                "NPM": format_pct(_pct(net_income, revenue)),
                "FCF": format_money_m(_usd_m(fcf)),
                "FCF Margin": format_pct(_pct(fcf, revenue)),
                "SBC / Revenue": format_pct(_pct(sbc, revenue)),
                "R&D / Revenue": format_pct(_pct(rd, revenue)),
                "Capex / Revenue": format_pct(_pct(capex, revenue)),
                "ROIC": format_pct(roic),
                "Shares": format_number(_shares_m(shares), 1),
            }
        )

    if rows:
        for metric in ("Revenue", "FCF", "ROIC"):
            if all(row.get(metric) == "N/A" for row in rows):
                data_gaps.append(f"확인 불가: {metric} XBRL 태그")
    return rows


def _invested_capital(series: dict[str, dict[int, dict[str, Any]]], year: int) -> float | None:
    equity = _value(series, "equity", year)
    cash = _value(series, "cash", year) or 0
    current_debt = _value(series, "debt_current", year) or 0
    long_debt = _value(series, "debt_long", year) or 0
    debt = current_debt + long_debt
    if equity is not None and (debt or cash):
        return debt + equity - cash
    assets = _value(series, "assets", year)
    liabilities = _value(series, "liabilities", year)
    if assets is not None and liabilities is not None:
        return assets - liabilities
    return None


def _roic(
    series: dict[str, dict[int, dict[str, Any]]],
    year: int,
    operating_income: float | None,
    invested_capital: float | None,
    previous_invested_capital: float | None,
) -> float | None:
    if operating_income is None or invested_capital in (None, 0):
        return None
    pretax = _value(series, "pretax_income", year)
    tax = _value(series, "tax_expense", year)
    tax_rate = 0.21
    if pretax not in (None, 0) and tax is not None:
        tax_rate = max(0.0, min(0.35, tax / pretax))
    denominator = invested_capital
    if previous_invested_capital not in (None, 0):
        denominator = (invested_capital + previous_invested_capital) / 2
    return operating_income * (1 - tax_rate) / denominator * 100


def _build_qoe_rows(series: dict[str, dict[int, dict[str, Any]]], years: list[int]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    previous_assets: float | None = None
    for year in years:
        net_income = _value(series, "net_income", year)
        cfo = _value(series, "cfo", year)
        capex_raw = _value(series, "capex", year)
        capex = abs(capex_raw) if capex_raw is not None else None
        fcf = cfo - capex if cfo is not None and capex is not None else None
        assets = _value(series, "assets", year)
        avg_assets = None
        if assets is not None and previous_assets is not None:
            avg_assets = (assets + previous_assets) / 2
        previous_assets = assets if assets is not None else previous_assets
        current_assets = _value(series, "current_assets", year)
        current_liabilities = _value(series, "current_liabilities", year)
        working_capital = None
        if current_assets is not None and current_liabilities is not None:
            working_capital = current_assets - current_liabilities

        rows.append(
            {
                "FY": f"FY{year}",
                "Accrual Ratio": format_pct(_pct(None if net_income is None or cfo is None else net_income - cfo, avg_assets)),
                "FCF / Net Income": format_pct(_pct(fcf, net_income)),
                "Working Capital": format_money_m(_usd_m(working_capital)),
                "SBC": format_money_m(_usd_m(_value(series, "sbc", year))),
                "D&A": format_money_m(_usd_m(_value(series, "dna", year))),
                "Deferred Tax": format_money_m(_usd_m(_value(series, "deferred_tax", year))),
                "ΔAR": format_money_m(_usd_m(_value(series, "ar_change", year))),
                "ΔInventory": format_money_m(_usd_m(_value(series, "inventory_change", year))),
                "ΔAP": format_money_m(_usd_m(_value(series, "ap_change", year))),
            }
        )
    return rows


def _build_capital_rows(series: dict[str, dict[int, dict[str, Any]]], years: list[int]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for year in years:
        rows.append(
            {
                "FY": f"FY{year}",
                "Buybacks": format_money_m(_usd_m(_value(series, "buybacks", year))),
                "Dividends": format_money_m(_usd_m(_value(series, "dividends", year))),
                "Acquisitions": format_money_m(_usd_m(_value(series, "acquisitions", year))),
                "Debt Issued": format_money_m(_usd_m(_value(series, "debt_issued", year))),
                "Debt Repaid": format_money_m(_usd_m(_value(series, "debt_repaid", year))),
                "Shares": format_number(_shares_m(_value(series, "shares", year)), 1),
            }
        )
    return rows


def _build_valuation_band_rows(
    series: dict[str, dict[int, dict[str, Any]]],
    years: list[int],
    price_history: list[tuple[str, float]],
) -> list[dict[str, Any]]:
    """5년 일별 주가 × 연간 EPS/주당매출로 trailing P/E·P/S 밴드를 근사 계산한다.

    각 거래일에는 그 시점에 공시가 완료된 가장 최근 회계연도 실적을 적용한다
    (회계연도 종료 후 90일 보고 지연 가정). 결과는 근사치이므로 라벨에 명시한다.
    """
    if not years or not price_history:
        return []
    fundamentals: list[tuple[str, float | None, float | None]] = []  # (적용 시작일, EPS, 주당매출)
    for year in years:
        end = str(series.get("net_income", {}).get(year, {}).get("end", "")) or f"{year}-12-31"
        available_from = _shift_date(end, days=90)
        net_income = _value(series, "net_income", year)
        revenue = _value(series, "revenue", year)
        shares = _value(series, "shares", year)
        eps = net_income / shares if net_income is not None and shares not in (None, 0) else None
        sales_ps = revenue / shares if revenue is not None and shares not in (None, 0) else None
        fundamentals.append((available_from, eps, sales_ps))
    fundamentals.sort(key=lambda item: item[0])

    pe_values: list[float] = []
    ps_values: list[float] = []
    for date_str, close in price_history:
        eps = sales_ps = None
        for available_from, fy_eps, fy_sales_ps in fundamentals:
            if available_from <= date_str:
                eps, sales_ps = fy_eps, fy_sales_ps
        if eps is not None and eps > 0:
            pe_values.append(close / eps)
        if sales_ps is not None and sales_ps > 0:
            ps_values.append(close / sales_ps)

    rows: list[dict[str, Any]] = []
    for metric, values in (("Trailing P/E (근사)", pe_values), ("P/S (근사)", ps_values)):
        if len(values) < 60:
            continue
        current = values[-1]
        ordered = sorted(values)
        rows.append(
            {
                "Metric": metric,
                "Current": format_x(current),
                "5Y Min": format_x(ordered[0]),
                "5Y P25": format_x(_percentile(ordered, 25)),
                "5Y Median": format_x(_percentile(ordered, 50)),
                "5Y P75": format_x(_percentile(ordered, 75)),
                "5Y Max": format_x(ordered[-1]),
                "Current Percentile": format_pct(sum(1 for v in ordered if v <= current) / len(ordered) * 100),
            }
        )
    return rows


def _shift_date(date_str: str, days: int) -> str:
    try:
        base = datetime.fromisoformat(date_str[:10])
    except ValueError:
        return date_str
    from datetime import timedelta

    return (base + timedelta(days=days)).date().isoformat()


def _percentile(ordered: list[float], pct: float) -> float:
    if not ordered:
        return float("nan")
    index = (len(ordered) - 1) * pct / 100
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = index - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def fetch_yfinance_market_data(ticker: str) -> dict[str, Any]:
    data_gaps: list[str] = []
    profile: dict[str, Any] = {}
    consensus_rows: list[dict[str, Any]] = []
    estimate_rows: list[dict[str, Any]] = []
    technical_rows: list[dict[str, Any]] = []
    peer_rows: list[dict[str, Any]] = []
    price_history: list[tuple[str, float]] = []

    def result(extra_gaps: list[str] | None = None) -> dict[str, Any]:
        return {
            "profile": {key: value for key, value in profile.items() if value is not None},
            "consensus_rows": consensus_rows,
            "estimate_rows": estimate_rows,
            "technical_rows": technical_rows,
            "peer_rows": peer_rows,
            "price_history": price_history,
            "data_gaps": [*data_gaps, *(extra_gaps or [])],
        }

    try:
        import yfinance as yf  # type: ignore
    except Exception:
        return result(["확인 불가: yfinance 패키지가 설치되지 않아 시장 데이터 수집 생략"])

    try:
        with _suppress_yfinance_pandas4_warning():
            ticker_obj = yf.Ticker(ticker)
            info = ticker_obj.info or {}
    except Exception as exc:
        return result([f"확인 불가: yfinance info 수집 실패 ({exc})"])

    profile = {
        "company_name": info.get("longName") or info.get("shortName"),
        "exchange": info.get("exchange"),
        "sector": info.get("sector"),
        "market_cap": info.get("marketCap"),
        "as_of": _format_yahoo_date(info.get("mostRecentQuarter")),
    }
    consensus_rows = [
        {"Metric": "Market Cap", "Value": format_money_b_from_raw(info.get("marketCap"))},
        {"Metric": "Forward P/E", "Value": format_x(info.get("forwardPE"))},
        {"Metric": "EV/EBITDA", "Value": format_x(info.get("enterpriseToEbitda"))},
        {"Metric": "EV/Sales", "Value": format_x(info.get("enterpriseToRevenue"))},
        {"Metric": "PEG", "Value": format_x(info.get("pegRatio") or info.get("trailingPegRatio"))},
        {"Metric": "Forward EPS", "Value": format_number(info.get("forwardEps"), 2)},
        {"Metric": "Revenue Growth", "Value": format_pct(_ratio_to_pct(info.get("revenueGrowth")))},
        {"Metric": "Analyst Target Mean", "Value": f"${format_number(info.get('targetMeanPrice'), 2)}"},
        {"Metric": "Analyst Count", "Value": format_number(info.get("numberOfAnalystOpinions"), 0)},
        {"Metric": "Recommendation", "Value": info.get("recommendationKey") or "N/A"},
    ]

    try:
        estimate_rows = _estimate_rows(ticker_obj)
    except Exception as exc:
        data_gaps.append(f"확인 불가: yfinance 애널리스트 추정치 수집 실패 ({exc})")
    if not estimate_rows:
        data_gaps.append("확인 불가: 애널리스트 상세 추정치(분기·연도별)")

    try:
        with _suppress_yfinance_pandas4_warning():
            history = ticker_obj.history(period="5y", auto_adjust=False)
            benchmark_history = yf.Ticker("SPY").history(period="5y", auto_adjust=False)
        technical_rows = _technical_rows_from_history(history, benchmark_history)
        price_history = _price_history_points(history)
    except Exception as exc:
        data_gaps.append(f"확인 불가: yfinance 가격 히스토리 수집 실패 ({exc})")

    try:
        peer_rows = _peer_rows(info)
        if not peer_rows:
            peer_rows = _fallback_peer_rows(yf, ticker)
        if not peer_rows:
            peer_rows = _industry_peer_rows(yf, ticker, info)
    except Exception:
        peer_rows = []
    if not peer_rows:
        data_gaps.append("확인 불가: yfinance에서 신뢰 가능한 피어 비교표를 제공하지 않음")

    return result()


_ESTIMATE_PERIOD_LABELS = {
    "0q": "현재 분기",
    "+1q": "차기 분기",
    "0y": "FY+1(당기)",
    "+1y": "FY+2(차기)",
}


def _estimate_rows(ticker_obj: Any) -> list[dict[str, Any]]:
    """yfinance 추정치 테이블(EPS·매출 컨센서스, 리비전, 목표주가 분포)을 행 목록으로 정리한다."""
    rows: list[dict[str, Any]] = []

    def frame_records(name: str) -> list[tuple[str, dict[str, Any]]]:
        try:
            with _suppress_yfinance_pandas4_warning():
                frame = getattr(ticker_obj, name)
        except Exception:
            return []
        if frame is None or getattr(frame, "empty", True):
            return []
        return [(str(index), record) for index, record in frame.to_dict("index").items()]

    for period, record in frame_records("earnings_estimate"):
        label = _ESTIMATE_PERIOD_LABELS.get(period, period)
        rows.append(
            {
                "Item": f"EPS 컨센서스 — {label}",
                "Avg": format_number(record.get("avg"), 2),
                "Low": format_number(record.get("low"), 2),
                "High": format_number(record.get("high"), 2),
                "Analysts": format_number(record.get("numberOfAnalysts"), 0),
                "YoY Growth": format_pct(_ratio_to_pct(record.get("growth"))),
            }
        )
    for period, record in frame_records("revenue_estimate"):
        label = _ESTIMATE_PERIOD_LABELS.get(period, period)
        rows.append(
            {
                "Item": f"매출 컨센서스 — {label}",
                "Avg": format_money_b_from_raw(record.get("avg")),
                "Low": format_money_b_from_raw(record.get("low")),
                "High": format_money_b_from_raw(record.get("high")),
                "Analysts": format_number(record.get("numberOfAnalysts"), 0),
                "YoY Growth": format_pct(_ratio_to_pct(record.get("growth"))),
            }
        )
    for period, record in frame_records("eps_trend"):
        label = _ESTIMATE_PERIOD_LABELS.get(period, period)
        rows.append(
            {
                "Item": f"EPS 리비전 — {label}",
                "Avg": format_number(record.get("current"), 2),
                "Low": f"30일 전 {format_number(record.get('30daysAgo'), 2)}",
                "High": f"90일 전 {format_number(record.get('90daysAgo'), 2)}",
                "Analysts": "N/A",
                "YoY Growth": "N/A",
            }
        )
    try:
        with _suppress_yfinance_pandas4_warning():
            targets = ticker_obj.analyst_price_targets or {}
    except Exception:
        targets = {}
    if targets.get("mean") is not None:
        rows.append(
            {
                "Item": "목표주가 분포",
                "Avg": f"${format_number(targets.get('mean'), 2)}",
                "Low": f"${format_number(targets.get('low'), 2)}",
                "High": f"${format_number(targets.get('high'), 2)}",
                "Analysts": f"중앙값 ${format_number(targets.get('median'), 2)}",
                "YoY Growth": f"현재가 ${format_number(targets.get('current'), 2)}",
            }
        )
    return rows


def _price_history_points(history: Any) -> list[tuple[str, float]]:
    if history is None or getattr(history, "empty", True):
        return []
    close = history["Close"].dropna()
    return [(str(index)[:10], float(value)) for index, value in close.items()]


@contextmanager
def _suppress_yfinance_pandas4_warning() -> Any:
    with warnings.catch_warnings():
        try:
            from pandas.errors import Pandas4Warning  # type: ignore
        except Exception:
            Pandas4Warning = Warning  # type: ignore
        warnings.filterwarnings(
            "ignore",
            message=r"Timestamp\.utcnow is deprecated.*",
            category=Pandas4Warning,
            module=r"yfinance\.scrapers\.quote",
        )
        yield


def _ratio_to_pct(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value) * 100
    except (TypeError, ValueError):
        return None


def _format_yahoo_date(value: Any) -> str | None:
    if value is None:
        return None
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return str(value)
    if timestamp <= 0:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat()


def _technical_rows_from_history(history: Any, benchmark_history: Any | None = None) -> list[dict[str, Any]]:
    if history is None or getattr(history, "empty", True):
        return []
    close = history["Close"].dropna()
    volume = history["Volume"].dropna() if "Volume" in history else None
    if close.empty:
        return []
    latest = float(close.iloc[-1])
    one_year = close.tail(252)
    rows = [
        {"Metric": "Latest Close", "Value": f"${latest:,.2f}"},
        {"Metric": "50D MA", "Value": f"${float(close.tail(50).mean()):,.2f}" if len(close) >= 50 else "N/A"},
        {"Metric": "200D MA", "Value": f"${float(close.tail(200).mean()):,.2f}" if len(close) >= 200 else "N/A"},
        {"Metric": "52W High", "Value": f"${float(one_year.max()):,.2f}" if not one_year.empty else "N/A"},
        {"Metric": "52W Low", "Value": f"${float(one_year.min()):,.2f}" if not one_year.empty else "N/A"},
        {"Metric": "1Y Return", "Value": format_pct((latest / float(one_year.iloc[0]) - 1) * 100) if len(one_year) > 1 else "N/A"},
    ]
    benchmark_return = _one_year_return(benchmark_history)
    stock_return = _one_year_return(history)
    if stock_return is not None and benchmark_return is not None:
        rows.append({"Metric": "Relative Strength vs SPY (1Y)", "Value": format_pct(stock_return - benchmark_return)})
    if volume is not None and not volume.empty:
        rows.append({"Metric": "Avg 30D Volume", "Value": format_number(float(volume.tail(30).mean()), 0)})
        if len(volume) >= 90:
            avg_30 = float(volume.tail(30).mean())
            avg_90 = float(volume.tail(90).mean())
            rows.append({"Metric": "Volume Trend 30D vs 90D", "Value": format_pct((avg_30 / avg_90 - 1) * 100) if avg_90 else "N/A"})
    supports, resistances = _support_resistance_levels([float(v) for v in one_year], latest)
    if supports:
        rows.append({"Metric": "Support Candidates (1Y swing lows)", "Value": ", ".join(f"${level:,.2f}" for level in supports)})
    if resistances:
        rows.append({"Metric": "Resistance Candidates (1Y swing highs)", "Value": ", ".join(f"${level:,.2f}" for level in resistances)})
    return rows


def _support_resistance_levels(
    closes: list[float],
    current: float,
    window: int = 10,
    merge_pct: float = 0.02,
    max_levels: int = 3,
) -> tuple[list[float], list[float]]:
    """최근 1년 종가의 스윙 고점/저점을 클러스터링해 지지·저항 후보 레벨을 계산한다."""
    if len(closes) < window * 2 + 1:
        return [], []
    extrema: list[float] = []
    for idx in range(window, len(closes) - window):
        segment = closes[idx - window : idx + window + 1]
        value = closes[idx]
        if value == max(segment) or value == min(segment):
            extrema.append(value)
    if not extrema:
        return [], []
    levels: list[float] = []
    for value in sorted(extrema):
        if levels and abs(value - levels[-1]) / levels[-1] <= merge_pct:
            levels[-1] = (levels[-1] + value) / 2
        else:
            levels.append(value)
    supports = sorted([level for level in levels if level < current], reverse=True)[:max_levels]
    resistances = sorted([level for level in levels if level >= current])[:max_levels]
    return supports, resistances


def _one_year_return(history: Any | None) -> float | None:
    if history is None or getattr(history, "empty", True):
        return None
    close = history["Close"].dropna()
    one_year = close.tail(252)
    if len(one_year) <= 1:
        return None
    return (float(one_year.iloc[-1]) / float(one_year.iloc[0]) - 1) * 100


def _peer_rows(info: dict[str, Any]) -> list[dict[str, Any]]:
    peers = info.get("peerInfo") or info.get("companyPeers") or []
    rows = []
    for peer in peers[:8]:
        if isinstance(peer, str):
            rows.append({"Peer": peer, "Note": "yfinance peer symbol only"})
        elif isinstance(peer, dict):
            rows.append({"Peer": peer.get("symbol") or peer.get("ticker") or "N/A", "Note": peer.get("name") or ""})
    return rows


def _fallback_peer_rows(yf: Any, ticker: str) -> list[dict[str, Any]]:
    return _peer_rows_from_symbols(yf, DEFAULT_PEERS.get(ticker.upper(), []))


def _industry_peer_rows(yf: Any, ticker: str, info: dict[str, Any]) -> list[dict[str, Any]]:
    """DEFAULT_PEERS에 없는 티커: 동일 industry 상위 기업(시장 비중순)을 피어로 사용한다."""
    industry_key = info.get("industryKey")
    if not industry_key:
        return []
    try:
        with _suppress_yfinance_pandas4_warning():
            top = yf.Industry(industry_key).top_companies
    except Exception:
        return []
    if top is None or getattr(top, "empty", True):
        return []
    symbols = [str(symbol) for symbol in top.index if str(symbol).upper() != ticker.upper()][:8]
    return _peer_rows_from_symbols(yf, symbols)[:5]


def _is_sane_peer(info: dict[str, Any]) -> bool:
    """데이터가 부실한 종목(OTC 마이크로캡 등)의 왜곡된 지표를 피어 비교에서 제외한다."""
    if not info.get("marketCap"):
        return False
    if not (info.get("shortName") or info.get("longName")):
        return False
    gross_margins = info.get("grossMargins")
    if gross_margins is not None and not 0 <= float(gross_margins) <= 1:
        return False
    ev_to_revenue = info.get("enterpriseToRevenue")
    if ev_to_revenue is not None and float(ev_to_revenue) > 100:
        return False
    return True


def _peer_rows_from_symbols(yf: Any, symbols: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for peer in symbols:
        try:
            with _suppress_yfinance_pandas4_warning():
                info = yf.Ticker(peer).info or {}
        except Exception:
            continue
        if not _is_sane_peer(info):
            continue
        rows.append(
            {
                "Peer": peer,
                "Company": info.get("shortName") or info.get("longName") or "N/A",
                "Market Cap": format_money_b_from_raw(info.get("marketCap")),
                "Revenue Growth": format_pct(_ratio_to_pct(info.get("revenueGrowth"))),
                "Gross Margin": format_pct(_ratio_to_pct(info.get("grossMargins"))),
                "Profit Margin": format_pct(_ratio_to_pct(info.get("profitMargins"))),
                "Forward P/E": format_x(info.get("forwardPE")),
                "EV/Sales": format_x(info.get("enterpriseToRevenue")),
            }
        )
    return rows
