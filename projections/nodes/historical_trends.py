"""
historical_trends.py — Historical Trends Analysis Node
=======================================================
Deterministic node that parses the multi-year I&E PSV to extract
3-5 year trends and compute trailing CAGRs for each line item.

Also extracts below-the-line data from CMIE Balance Sheet, Capex,
Capital History, and Cash Flow for depreciation, interest, tax, and EPS projections.
"""

from __future__ import annotations

import statistics
from typing import Any, Dict

from provess_client.ie_parser import parse_ie_psv_all_years, compute_cagrs


def _extract_tax_rate_history(all_years_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract effective tax rates over time and classify as stable or volatile.
    If std dev < 3pp → stable (use avg). If ≥ 3pp → volatile (needs agent analysis).
    """
    all_items = all_years_data.get("all_items_by_year", {})
    fiscal_years = all_years_data.get("fiscal_years", [])

    # Find tax and PBT lines
    tax_values = {}
    pbt_values = {}
    for label, year_data in all_items.items():
        label_lower = label.lower()
        if "provision for tax" in label_lower or "tax on" in label_lower:
            tax_values = year_data
        elif "profit before tax" in label_lower or "profit before extra" in label_lower:
            pbt_values = year_data

    if not tax_values or not pbt_values:
        return {"status": "no_data", "rates": {}, "avg_rate": None, "is_stable": True}

    # Compute effective tax rate per year
    rates = {}
    for fy in fiscal_years:
        if fy in tax_values and fy in pbt_values and pbt_values[fy] > 0:
            rate = (abs(tax_values[fy]) / abs(pbt_values[fy])) * 100
            rates[fy] = round(rate, 2)

    if len(rates) < 2:
        return {"status": "insufficient_data", "rates": rates, "avg_rate": None, "is_stable": True}

    rate_list = list(rates.values())
    avg_rate = round(statistics.mean(rate_list), 2)
    std_dev = round(statistics.stdev(rate_list), 2) if len(rate_list) > 1 else 0.0

    return {
        "status": "ok",
        "rates": rates,
        "avg_rate": avg_rate,
        "std_dev": std_dev,
        "is_stable": std_dev < 3.0,  # < 3 percentage points = stable
    }


def _extract_depreciation_data(
    balance_sheet_psv: str | None,
    capex_psv: str | None,
) -> Dict[str, Any]:
    """Extract gross block, accumulated depreciation, and capex data for D&A projection."""
    # Placeholder: parse Balance Sheet PSV for gross block + accumulated dep
    # Parse Capex PSV for capex plans
    # This will be fleshed out when we have sample CMIE data
    result = {
        "gross_block": None,
        "accumulated_depreciation": None,
        "capex_plan": None,
        "historical_dep_rate": None,
    }

    if balance_sheet_psv:
        # Quick extraction of key Balance Sheet items
        for line in balance_sheet_psv.split("\n"):
            cells = line.split("|")
            if len(cells) >= 2:
                label = cells[0].strip().lower()
                if "gross block" in label or "gross fixed" in label:
                    try:
                        result["gross_block"] = float(cells[-1].strip().replace(",", ""))
                    except (ValueError, IndexError):
                        pass
                elif "depreciation" in label and "accumulated" in label:
                    try:
                        result["accumulated_depreciation"] = float(cells[-1].strip().replace(",", ""))
                    except (ValueError, IndexError):
                        pass

    return result


def _extract_debt_and_interest_data(
    balance_sheet_psv: str | None,
    cash_flow_psv: str | None,
) -> Dict[str, Any]:
    """Extract borrowings and interest data for interest expense projection."""
    result = {
        "total_borrowings": None,
        "effective_interest_rate": None,
        "debt_changes": None,
    }

    if balance_sheet_psv:
        for line in balance_sheet_psv.split("\n"):
            cells = line.split("|")
            if len(cells) >= 2:
                label = cells[0].strip().lower()
                if "borrowing" in label or "total debt" in label:
                    try:
                        result["total_borrowings"] = float(cells[-1].strip().replace(",", ""))
                    except (ValueError, IndexError):
                        pass

    return result


def _extract_shares_data(capital_history_psv: str | None) -> Dict[str, Any]:
    """Extract shares outstanding and dilution history for EPS projection."""
    result = {
        "current_shares_outstanding": None,
        "dilution_events": [],
        "has_dilution_history": False,
    }

    # Parse Capital History Summary for equity events
    if capital_history_psv:
        for line in capital_history_psv.split("\n"):
            lower = line.lower()
            if any(kw in lower for kw in ["bonus", "split", "rights", "qip", "esop", "fpo"]):
                result["dilution_events"].append(line.strip())

        result["has_dilution_history"] = len(result["dilution_events"]) > 0

    return result


async def historical_trends_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse multi-year I&E data and compute trailing CAGRs.
    Also extract below-the-line data from CMIE reports.
    """
    company = state.get("company_name", "")
    print(f"\n{'='*60}")
    print(f"📈 HISTORICAL TRENDS: {company}")
    print(f"{'='*60}")

    ie_psv = state.get("income_expenditure_psv", "")

    # ── Multi-year I&E trends ──
    all_years_data = parse_ie_psv_all_years(ie_psv) if ie_psv else {}
    cagrs = compute_cagrs(all_years_data) if all_years_data.get("fiscal_years") else {}

    fiscal_years = all_years_data.get("fiscal_years", [])
    print(f"  📊 Fiscal years: {fiscal_years}")
    print(f"  📊 CAGRs computed: {len(cagrs)} items")
    for item, cagr in cagrs.items():
        print(f"     {item}: {cagr}%")

    # ── Tax rate analysis ──
    tax_analysis = _extract_tax_rate_history(all_years_data)
    if tax_analysis["status"] == "ok":
        print(f"  📊 Tax rate: avg {tax_analysis['avg_rate']}%, std {tax_analysis['std_dev']}pp → {'STABLE' if tax_analysis['is_stable'] else 'VOLATILE'}")

    # ── Below-the-line data ──
    depreciation_data = _extract_depreciation_data(
        state.get("balance_sheet_data"),
        state.get("capex_data"),
    )
    debt_data = _extract_debt_and_interest_data(
        state.get("balance_sheet_data"),
        state.get("cash_flow_data"),
    )
    shares_data = _extract_shares_data(state.get("capital_history_data"))

    if shares_data["has_dilution_history"]:
        print(f"  ⚠️ Dilution events found: {len(shares_data['dilution_events'])}")
    else:
        print("  ✅ No equity dilution events detected")

    return {
        "historical_analysis": {
            "fiscal_years": fiscal_years,
            "revenue_by_year": all_years_data.get("revenue_by_year", {}),
            "line_items_by_year": all_years_data.get("line_items_by_year", {}),
            "cagrs": cagrs,
            "tax_analysis": tax_analysis,
            "depreciation_data": depreciation_data,
            "debt_data": debt_data,
            "shares_data": shares_data,
        }
    }
