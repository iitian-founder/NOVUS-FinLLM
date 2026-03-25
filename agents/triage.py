# agents/triage.py
"""
Agent 1: Triage Agent (Phases 1 & 2 — Idea Screening & Kill Screen)

Type: Router / Gatekeeper
Speed: High
Cost: Very Low (no LLM calls)

This agent executes the Kill Screen as a deterministic Python rule-engine
using financial data ALREADY scraped by the main pipeline from Screener.in.
Zero LLM cost consumed. Zero extra network calls.
"""

from dataclasses import dataclass, field
from typing import Optional


# ── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class TriageInput:
    """
    Data needed for the Kill Screen.
    Populated from the pipeline's already-fetched Screener.in financial data.
    """
    ticker: str
    # From P&L data (multi-year)
    revenue_values: list[float] = field(default_factory=list)
    pat_values: list[float] = field(default_factory=list)
    ocf_values: list[float] = field(default_factory=list)  # Operating Cash Flow
    depreciation_values: list[float] = field(default_factory=list)
    interest_values: list[float] = field(default_factory=list)
    ebit_values: list[float] = field(default_factory=list)

    # From BS data
    debt_equity_ratio: Optional[float] = None
    total_debt: float = 0.0
    total_equity: float = 0.0

    # Computed or optional
    promoter_holding_pct: Optional[float] = None
    promoter_pledge_pct: Optional[float] = None


@dataclass
class TriageResult:
    """Output of the Kill Screen."""
    ticker: str
    passed: bool
    kill_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    data_gaps: list[str] = field(default_factory=list)
    health_metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "passed": self.passed,
            "kill_reasons": self.kill_reasons,
            "warnings": self.warnings,
            "data_gaps": self.data_gaps,
            "health_metrics": self.health_metrics,
        }


# ── Helper Functions ─────────────────────────────────────────────────────────

def _calculate_cagr(start: float, end: float, years: int) -> Optional[float]:
    if start <= 0 or end <= 0 or years <= 0:
        return None
    return ((end / start) ** (1.0 / years) - 1.0) * 100


def _count_negative_years(values: list[float]) -> int:
    return sum(1 for v in values if v < 0)


def _count_profit_but_no_cash(pat_vals: list[float], ocf_vals: list[float]) -> int:
    """Count years where PAT > 0 but OCF < 0 (earnings quality red flag)."""
    count = 0
    for pat, ocf in zip(pat_vals, ocf_vals):
        if pat > 0 and ocf < 0:
            count += 1
    return count


# ── Core Kill Screen ────────────────────────────────────────────────────────

def run_kill_screen(data: TriageInput) -> TriageResult:
    """
    Execute the deterministic Kill Screen using financial data
    already fetched by the pipeline.

    Returns a TriageResult indicating pass/fail and all reasons.

    Design Principle: Every rupee of LLM compute saved at Phase 2
    is a rupee available for deep analysis at Phase 5. Gate ruthlessly.
    """
    result = TriageResult(ticker=data.ticker, passed=True)

    # ── 1. Revenue Decline Check ──
    if len(data.revenue_values) >= 3:
        rev = data.revenue_values
        recent_3 = rev[-3:]
        # Check if revenue declined for 2+ consecutive years
        declines = sum(1 for i in range(1, len(recent_3)) if recent_3[i] < recent_3[i-1])
        if declines >= 2:
            result.kill_reasons.append(
                f"KILL: Revenue declined in {declines} of last {len(recent_3)} years. "
                f"Structural demand issue."
            )
            result.passed = False

        # 5-year revenue CAGR
        if len(rev) >= 6:
            cagr = _calculate_cagr(rev[-6], rev[-1], 5)
            if cagr is not None:
                result.health_metrics["revenue_cagr_5y"] = round(cagr, 1)
                if cagr < 5:
                    result.warnings.append(
                        f"WARNING: 5Y revenue CAGR is only {cagr:.1f}%. "
                        f"Below minimum growth threshold."
                    )
    else:
        result.data_gaps.append("Less than 3 years of revenue data available.")

    # ── 2. Negative PAT Check ──
    if data.pat_values:
        neg_pat_years = _count_negative_years(data.pat_values[-5:])
        result.health_metrics["negative_pat_years_of_5"] = neg_pat_years
        if neg_pat_years >= 3:
            result.kill_reasons.append(
                f"KILL: Net profit negative in {neg_pat_years} of last 5 years. "
                f"Company is not consistently profitable."
            )
            result.passed = False
        elif neg_pat_years >= 2:
            result.warnings.append(
                f"WARNING: Net profit negative in {neg_pat_years} of last 5 years."
            )

    # ── 3. Cash Flow vs Profit Mismatch ──
    if data.pat_values and data.ocf_values:
        mismatch = _count_profit_but_no_cash(
            data.pat_values[-5:], data.ocf_values[-5:]
        )
        result.health_metrics["profit_but_no_cash_years"] = mismatch
        if mismatch >= 3:
            result.kill_reasons.append(
                f"KILL: Positive PAT but negative CFO in {mismatch} of last 5 years. "
                f"Earnings quality is questionable."
            )
            result.passed = False
        elif mismatch >= 2:
            result.warnings.append(
                f"WARNING: PAT positive but CFO negative in {mismatch} years. "
                f"Earnings may not be backed by cash."
            )
    else:
        result.data_gaps.append(
            "Operating cash flow data not available — "
            "cannot verify earnings quality vs cash flow."
        )

    # ── 4. High Debt Check ──
    if data.total_equity > 0 and data.total_debt > 0:
        de_ratio = data.total_debt / data.total_equity
        result.health_metrics["debt_equity_ratio"] = round(de_ratio, 2)
        if de_ratio > 3.0:
            result.kill_reasons.append(
                f"KILL: Debt/Equity ratio = {de_ratio:.1f}x. "
                f"Extreme leverage — one downturn could wipe equity."
            )
            result.passed = False
        elif de_ratio > 1.5:
            result.warnings.append(
                f"WARNING: Debt/Equity ratio = {de_ratio:.1f}x. Leverage is elevated."
            )
    elif data.debt_equity_ratio is not None:
        result.health_metrics["debt_equity_ratio"] = data.debt_equity_ratio
        if data.debt_equity_ratio > 3.0:
            result.kill_reasons.append(
                f"KILL: Debt/Equity ratio = {data.debt_equity_ratio:.1f}x. Extreme leverage."
            )
            result.passed = False
        elif data.debt_equity_ratio > 1.5:
            result.warnings.append(
                f"WARNING: Debt/Equity ratio = {data.debt_equity_ratio:.1f}x."
            )
    else:
        result.data_gaps.append("Debt/Equity data not available.")

    # ── 5. Interest Coverage Check ──
    if data.ebit_values and data.interest_values:
        latest_ebit = data.ebit_values[-1]
        latest_interest = data.interest_values[-1]
        if latest_interest > 0:
            ic = latest_ebit / latest_interest
            result.health_metrics["interest_coverage"] = round(ic, 1)
            if ic < 1.5:
                result.kill_reasons.append(
                    f"KILL: Interest coverage = {ic:.1f}x. "
                    f"Company may not be able to service its debt."
                )
                result.passed = False
            elif ic < 3.0:
                result.warnings.append(
                    f"WARNING: Interest coverage = {ic:.1f}x. Debt servicing is tight."
                )

    # ── 6. Promoter Pledge Check (if available) ──
    if data.promoter_pledge_pct is not None:
        result.health_metrics["promoter_pledge_pct"] = data.promoter_pledge_pct
        if data.promoter_pledge_pct > 30:
            result.kill_reasons.append(
                f"KILL: Promoter pledge = {data.promoter_pledge_pct:.0f}% of holdings. "
                f"One margin call can destroy value."
            )
            result.passed = False
        elif data.promoter_pledge_pct > 15:
            result.warnings.append(
                f"WARNING: Promoter pledge at {data.promoter_pledge_pct:.0f}%."
            )
    else:
        result.data_gaps.append(
            "Promoter pledge data not available — requires manual check."
        )

    # ── 7. Low Promoter Holding Check ──
    if data.promoter_holding_pct is not None:
        result.health_metrics["promoter_holding_pct"] = data.promoter_holding_pct
        if data.promoter_holding_pct < 25:
            result.warnings.append(
                f"WARNING: Promoter holding = {data.promoter_holding_pct:.0f}%. "
                f"Very low alignment."
            )
    else:
        result.data_gaps.append("Promoter holding data not available.")

    # ── 8. Shrinking Margins Check ──
    if data.ebit_values and data.revenue_values and len(data.ebit_values) >= 3:
        margins = []
        for ebit, rev in zip(data.ebit_values[-3:], data.revenue_values[-3:]):
            if rev > 0:
                margins.append(ebit / rev * 100)
        if len(margins) >= 3:
            margin_declines = sum(
                1 for i in range(1, len(margins)) if margins[i] < margins[i-1]
            )
            if margin_declines >= 2:
                result.warnings.append(
                    f"WARNING: Operating margins declining for {margin_declines} "
                    f"consecutive years ({margins[0]:.1f}% → {margins[-1]:.1f}%)."
                )

    return result


# ── Helper: Build TriageInput from Pipeline Data ─────────────────────────────

def build_triage_input_from_financial_data(
    ticker: str,
    pl_data: dict,      # Output of extract_financial_data_from_html(pl_html)
    bs_data: dict = None, # Output of extract_financial_data_from_html(bs_html)
) -> TriageInput:
    """
    Convert the pipeline's already-fetched Screener.in data into TriageInput.
    No extra network calls needed.
    """
    triage = TriageInput(ticker=ticker)

    # Sort years (exclude TTM)
    years = sorted([y for y in pl_data.keys() if 'ttm' not in y.lower()])

    for yr in years:
        yr_data = pl_data[yr]
        triage.revenue_values.append(yr_data.get('Sales+', 0))
        triage.pat_values.append(yr_data.get('Net Profit+', 0))
        triage.ebit_values.append(yr_data.get('Operating Profit', 0))
        triage.interest_values.append(yr_data.get('Interest', 0))
        triage.depreciation_values.append(yr_data.get('Depreciation', 0))

        # OCF if available in P&L (some Screener pages include it)
        ocf = yr_data.get('Cash from Operating Activity', None) or \
              yr_data.get('Cash from Operating Activity+', None)
        if ocf is not None:
            triage.ocf_values.append(ocf)

    # Balance sheet data
    if bs_data:
        bs_years = sorted([y for y in bs_data.keys() if 'ttm' not in y.lower()])
        if bs_years:
            latest_bs = bs_data[bs_years[-1]]
            triage.total_debt = latest_bs.get('Borrowings', 0)
            equity_capital = latest_bs.get('Equity Capital', 0)
            reserves = latest_bs.get('Reserves', 0)
            triage.total_equity = equity_capital + reserves
            if triage.total_equity > 0:
                triage.debt_equity_ratio = round(
                    triage.total_debt / triage.total_equity, 2
                )

    return triage
