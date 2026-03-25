# agents/forensic_quant.py
"""
Agent 3: Forensic Quant Agent (Phases 6 & 7 — Financial Forensics & Valuation)

Type: Code Execution Agent
Mode: Zero creativity. Pure math. No LLM narrative allowed in this agent's core loop.

Law 2 of FinLLM Safety: Python calculates. LLM narrates. Never mix.
The LLM must NEVER be asked to calculate a ratio directly.
"""

import json
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional


# ── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class ForensicScorecard:
    """
    Structured output of all financial forensics.
    This is passed to Agent 5 (PM Synthesis) for thesis generation.
    """
    ticker: str

    # Profitability
    roic_5y_avg: Optional[float] = None
    roic_trend: str = "unknown"   # "improving", "stable", "deteriorating", "unknown"
    roe_latest: Optional[float] = None
    roce_latest: Optional[float] = None

    # DuPont Decomposition
    dupont_net_margin: Optional[float] = None
    dupont_asset_turnover: Optional[float] = None
    dupont_equity_multiplier: Optional[float] = None
    dupont_roe_driver: str = "unknown"  # "margin", "turnover", "leverage"

    # Earnings Quality
    fcf_pat_ratio_5y_avg: Optional[float] = None
    ocf_ebitda_ratio_latest: Optional[float] = None
    earnings_quality: str = "UNKNOWN"  # "HIGH", "MEDIUM", "LOW", "UNKNOWN"
    accrual_ratio: Optional[float] = None

    # Working Capital
    ccc_latest: Optional[float] = None  # Cash Conversion Cycle (days)
    ccc_trend: str = "unknown"
    working_capital_pct_revenue: Optional[float] = None

    # Leverage
    net_debt_ebitda: Optional[float] = None
    interest_coverage: Optional[float] = None
    debt_equity: Optional[float] = None

    # Valuation
    reverse_dcf_implied_growth: Optional[float] = None

    # Revenue Quality
    revenue_cagr_5y: Optional[float] = None
    revenue_cagr_3y: Optional[float] = None

    # Flags and warnings
    flags: list[str] = field(default_factory=list)
    data_gaps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to dict for JSON output."""
        return {
            "ticker": self.ticker,
            "profitability": {
                "roic_5y_avg": self.roic_5y_avg,
                "roic_trend": self.roic_trend,
                "roe_latest": self.roe_latest,
                "roce_latest": self.roce_latest,
            },
            "dupont": {
                "net_margin": self.dupont_net_margin,
                "asset_turnover": self.dupont_asset_turnover,
                "equity_multiplier": self.dupont_equity_multiplier,
                "roe_driver": self.dupont_roe_driver,
            },
            "earnings_quality": {
                "fcf_pat_ratio_5y_avg": self.fcf_pat_ratio_5y_avg,
                "ocf_ebitda_ratio_latest": self.ocf_ebitda_ratio_latest,
                "quality_grade": self.earnings_quality,
                "accrual_ratio": self.accrual_ratio,
            },
            "working_capital": {
                "ccc_latest_days": self.ccc_latest,
                "ccc_trend": self.ccc_trend,
                "wc_pct_revenue": self.working_capital_pct_revenue,
            },
            "leverage": {
                "net_debt_ebitda": self.net_debt_ebitda,
                "interest_coverage": self.interest_coverage,
                "debt_equity": self.debt_equity,
            },
            "valuation": {
                "reverse_dcf_implied_growth": self.reverse_dcf_implied_growth,
            },
            "revenue": {
                "cagr_5y": self.revenue_cagr_5y,
                "cagr_3y": self.revenue_cagr_3y,
            },
            "flags": self.flags,
            "data_gaps": self.data_gaps,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


# ── Pure Math Functions ──────────────────────────────────────────────────────
# Law 2: Python calculates. LLM narrates. Never mix.

def dupont_decomposition(
    revenue: float,
    pat: float,
    avg_total_assets: float,
    avg_equity: float,
) -> dict:
    """
    DuPont ROE decomposition — pure Python, no LLM.
    
    ROE = Net Margin × Asset Turnover × Equity Multiplier
    
    A 25% ROE from 5% margin × 5x leverage is VERY different
    from 25% ROE from 25% margin × 1x turnover × 1x leverage.
    """
    if revenue <= 0 or avg_total_assets <= 0 or avg_equity <= 0:
        return {
            "roe": None,
            "net_margin": None,
            "asset_turnover": None,
            "equity_multiplier": None,
            "roe_driver": "insufficient_data",
        }

    net_margin = pat / revenue
    asset_turnover = revenue / avg_total_assets
    equity_multiplier = avg_total_assets / avg_equity
    roe = net_margin * asset_turnover * equity_multiplier

    # Classify the primary driver
    if net_margin > 0.15:
        driver = "margin"     # Pricing power / efficiency (BEST)
    elif equity_multiplier > 2.5:
        driver = "leverage"   # Financial engineering (DANGEROUS)
    else:
        driver = "turnover"   # Capital efficiency (GOOD)

    return {
        "roe": round(roe, 4),
        "net_margin": round(net_margin, 4),
        "asset_turnover": round(asset_turnover, 4),
        "equity_multiplier": round(equity_multiplier, 4),
        "roe_driver": driver,
    }


def reverse_dcf_implied_growth(
    market_cap: float,
    fcf_base: float,
    wacc: float = 0.12,
    terminal_growth: float = 0.05,
    projection_years: int = 10,
) -> Optional[float]:
    """
    Solve for the revenue/FCF CAGR that justifies current market cap.
    
    Design principle: Never ask an LLM to project Year 7 FCF from scratch.
    Instead, ALWAYS run Reverse DCF first: give the model the current market cap
    and let Python calculate the exact growth rate the market is already pricing in.
    That's the mathematical ground truth.
    """
    if market_cap <= 0 or fcf_base <= 0 or wacc <= terminal_growth:
        return None

    lo, hi = 0.0, 0.50
    for _ in range(100):  # Binary search
        mid = (lo + hi) / 2
        dcf_val = sum(
            fcf_base * (1 + mid) ** t / (1 + wacc) ** t
            for t in range(1, projection_years + 1)
        )
        # Terminal value
        terminal_fcf = fcf_base * (1 + mid) ** projection_years
        terminal_value = terminal_fcf * (1 + terminal_growth) / (wacc - terminal_growth)
        pv_terminal = terminal_value / (1 + wacc) ** projection_years
        dcf_val += pv_terminal

        if dcf_val < market_cap:
            lo = mid
        else:
            hi = mid

        if abs(hi - lo) < 0.0001:
            break

    return round((lo + hi) / 2, 4)


def calculate_cagr(start_value: float, end_value: float, years: int) -> Optional[float]:
    """Calculate CAGR between two values over N years."""
    if start_value <= 0 or end_value <= 0 or years <= 0:
        return None
    try:
        cagr = (end_value / start_value) ** (1.0 / years) - 1.0
        return round(cagr * 100, 2)  # Return as percentage
    except Exception:
        return None


def classify_earnings_quality(
    ocf_ebitda_ratio: Optional[float],
    fcf_pat_ratio: Optional[float],
    accrual_ratio: Optional[float],
) -> str:
    """
    Classify earnings quality based on cash flow metrics.
    
    Earnings Quality Score:
    - CFO/EBITDA ratio (should be >70% consistently)
    - FCF/PAT ratio (should be >60%)
    - Accrual ratio: (Net Income - CFO) / Total Assets
      High accrual ratio = low earnings quality
    """
    score = 0
    checks = 0

    if ocf_ebitda_ratio is not None:
        checks += 1
        if ocf_ebitda_ratio >= 0.70:
            score += 2
        elif ocf_ebitda_ratio >= 0.50:
            score += 1

    if fcf_pat_ratio is not None:
        checks += 1
        if fcf_pat_ratio >= 0.60:
            score += 2
        elif fcf_pat_ratio >= 0.40:
            score += 1

    if accrual_ratio is not None:
        checks += 1
        if abs(accrual_ratio) <= 0.05:
            score += 2  # Low accruals = high quality
        elif abs(accrual_ratio) <= 0.10:
            score += 1

    if checks == 0:
        return "UNKNOWN"

    avg_score = score / checks
    if avg_score >= 1.5:
        return "HIGH"
    elif avg_score >= 0.8:
        return "MEDIUM"
    else:
        return "LOW"


def classify_trend(values: list[float]) -> str:
    """Classify the trend of a series of values."""
    if not values or len(values) < 2:
        return "unknown"

    clean = [v for v in values if v is not None and np.isfinite(v)]
    if len(clean) < 2:
        return "unknown"

    # Simple linear regression slope
    x = np.arange(len(clean))
    try:
        slope = np.polyfit(x, clean, 1)[0]
        avg_val = np.mean(clean)
        if avg_val == 0:
            return "stable"
        relative_slope = slope / abs(avg_val)

        if relative_slope > 0.03:
            return "improving"
        elif relative_slope < -0.03:
            return "deteriorating"
        else:
            return "stable"
    except Exception:
        return "unknown"


# ── Main Pipeline Entry Point ────────────────────────────────────────────────

def run_forensic_analysis(
    ticker: str,
    financial_data: dict,           # P&L data from extract_financial_data_from_html
    balance_sheet_data: dict = None, # BS data
    market_cap: float = None,       # Current market cap in crores
    latest_fcf: float = None,       # Latest free cash flow
) -> ForensicScorecard:
    """
    Run the full forensic quant analysis pipeline.
    
    Input: Clean financial data (from Agent 2 or existing scrapers).
    Output: ForensicScorecard with all metrics computed via pure Python.
    
    This agent has ZERO creativity. Pure math. No LLM narrative.
    """
    scorecard = ForensicScorecard(ticker=ticker)

    # Get available years (sorted ascending)
    years = sorted([y for y in financial_data.keys() if 'ttm' not in y.lower()])

    if not years:
        scorecard.data_gaps.append("No valid yearly data available.")
        return scorecard

    latest_year = years[-1]
    latest = financial_data[latest_year]

    # ── Revenue CAGR ──
    if len(years) >= 6:
        rev_start = financial_data[years[-6]].get('Sales+', 0)
        rev_end = latest.get('Sales+', 0)
        scorecard.revenue_cagr_5y = calculate_cagr(rev_start, rev_end, 5)

    if len(years) >= 4:
        rev_start = financial_data[years[-4]].get('Sales+', 0)
        rev_end = latest.get('Sales+', 0)
        scorecard.revenue_cagr_3y = calculate_cagr(rev_start, rev_end, 3)

    # ── DuPont Decomposition ──
    revenue = latest.get('Sales+', 0)
    pat = latest.get('Net Profit+', 0)

    if balance_sheet_data and latest_year in balance_sheet_data:
        bs = balance_sheet_data[latest_year]
        total_assets = bs.get('Total Assets', 0) or bs.get('Total', 0)
        equity = bs.get('Equity Capital', 0) + bs.get('Reserves', 0)

        if total_assets > 0 and equity > 0:
            dp = dupont_decomposition(revenue, pat, total_assets, equity)
            scorecard.dupont_net_margin = dp.get("net_margin")
            scorecard.dupont_asset_turnover = dp.get("asset_turnover")
            scorecard.dupont_equity_multiplier = dp.get("equity_multiplier")
            scorecard.dupont_roe_driver = dp.get("roe_driver", "unknown")
            scorecard.roe_latest = dp.get("roe")

            # Debt / Equity
            total_debt = bs.get('Borrowings', 0)
            if equity > 0:
                scorecard.debt_equity = round(total_debt / equity, 2)
    else:
        scorecard.data_gaps.append("Balance sheet data not available for DuPont decomposition.")

    # ── Earnings Quality ──
    ebitda = latest.get('Operating Profit', 0) + latest.get('Depreciation', 0)
    ocf = latest.get('Cash from Operating Activity', None) or latest.get('Cash from Operating Activity+', None)

    if ocf is not None and ebitda > 0:
        scorecard.ocf_ebitda_ratio_latest = round(ocf / ebitda, 2)

    capex = latest.get('Fixed Assets Purchased', None) or latest.get('Purchase of Fixed Assets', None)
    if ocf is not None and capex is not None:
        fcf = ocf - abs(capex)
        if pat > 0:
            scorecard.fcf_pat_ratio_5y_avg = round(fcf / pat, 2)

    if ocf is not None and pat != 0:
        total_assets_val = 0
        if balance_sheet_data and latest_year in balance_sheet_data:
            total_assets_val = balance_sheet_data[latest_year].get('Total Assets', 0) or 1
        if total_assets_val > 0:
            scorecard.accrual_ratio = round((pat - ocf) / total_assets_val, 4)

    scorecard.earnings_quality = classify_earnings_quality(
        scorecard.ocf_ebitda_ratio_latest,
        scorecard.fcf_pat_ratio_5y_avg,
        scorecard.accrual_ratio,
    )

    # ── Interest Coverage ──
    ebit = latest.get('Operating Profit', 0)
    interest = latest.get('Interest', 0)
    if interest > 0:
        scorecard.interest_coverage = round(ebit / interest, 2)

    # ── Net Debt / EBITDA ──
    if balance_sheet_data and latest_year in balance_sheet_data:
        bs = balance_sheet_data[latest_year]
        total_debt = bs.get('Borrowings', 0)
        cash = bs.get('Cash Equivalents', 0) or bs.get('Investments', 0) * 0.3  # conservative
        net_debt = total_debt - cash
        if ebitda > 0:
            scorecard.net_debt_ebitda = round(net_debt / ebitda, 2)

    # ── Reverse DCF ──
    if market_cap and latest_fcf and latest_fcf > 0:
        scorecard.reverse_dcf_implied_growth = reverse_dcf_implied_growth(
            market_cap=market_cap,
            fcf_base=latest_fcf,
        )

    # ── Flags ──
    # Q4 revenue spike detection (channel stuffing indicator)
    if len(years) >= 2:
        for i in range(max(0, len(years) - 3), len(years)):
            yr = years[i]
            yr_rev = financial_data[yr].get('Sales+', 0)
            if yr_rev > 0:
                prev_yr_rev = financial_data.get(years[max(0, i-1)], {}).get('Sales+', 0)
                if prev_yr_rev > 0 and yr_rev / prev_yr_rev > 1.3:
                    scorecard.flags.append(f"Revenue jump > 30% in {yr} — verify organic vs. channel stuffing")

    # Capex vs Depreciation check
    if capex is not None:
        dep = latest.get('Depreciation', 0)
        if dep > 0 and abs(capex) > dep * 3:
            scorecard.flags.append(f"Capex/Depreciation > 3x in {latest_year} — verify growth vs. vanity projects")

    if scorecard.interest_coverage is not None and scorecard.interest_coverage < 3:
        scorecard.flags.append(f"Interest coverage < 3x ({scorecard.interest_coverage}x) — debt servicing risk")

    if scorecard.earnings_quality == "LOW":
        scorecard.flags.append("Earnings quality classified as LOW — cash flow does not support reported profits")

    return scorecard
