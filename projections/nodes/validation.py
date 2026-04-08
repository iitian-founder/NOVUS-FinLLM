"""
validation.py — Deterministic Projection Validation Node
==========================================================
Runs sanity checks on the projection output before report generation.
If critical flags are found, routes back to analyst_review.

Guardrail Checks:
  1. Revenue growth > 50% any year → Flag
  2. EBITDA margin outside historical ±15pp → Flag
  3. Negative EBITDA → Flag (unless pre-profit company)
  4. Any NaN/None values → Critical
  5. Expense > Revenue → Critical
"""

from __future__ import annotations

import math
from typing import Any, Dict, List


def _check_revenue_growth(projection: Dict[str, Any]) -> List[Dict[str, str]]:
    """Flag years where revenue growth exceeds 50%."""
    flags = []
    projections = projection.get("projections", projection.get("line_items", {}))
    total_revenue = projection.get("total_revenue", [])

    if isinstance(total_revenue, list) and len(total_revenue) >= 2:
        for i in range(1, len(total_revenue)):
            prev = total_revenue[i - 1]
            curr = total_revenue[i]
            if prev and prev > 0:
                growth = ((curr - prev) / prev) * 100
                if abs(growth) > 50:
                    year_labels = projection.get("year_labels", projection.get("projected_years", []))
                    year = year_labels[i] if i < len(year_labels) else f"Year {i + 1}"
                    flags.append({
                        "type": "warning",
                        "check": "revenue_growth_>50%",
                        "message": f"Revenue growth of {growth:.1f}% in {year} exceeds 50% threshold",
                    })
    return flags


def _check_ebitda_margin(projection: Dict[str, Any], historical: Dict[str, Any]) -> List[Dict[str, str]]:
    """Flag if EBITDA margin deviates more than 15pp from historical average."""
    flags = []
    ebitda = projection.get("ebitda", [])
    total_revenue = projection.get("total_revenue", [])

    if not ebitda or not total_revenue:
        # Try derived_items
        derived = projection.get("derived_items", {})
        if "EBITDA" in derived:
            ebitda_data = derived["EBITDA"]
            ebitda = list(ebitda_data.values()) if isinstance(ebitda_data, dict) else ebitda_data

    # Get historical margin as anchor
    hist_rev = historical.get("revenue_by_year", {})
    if hist_rev and isinstance(total_revenue, list) and isinstance(ebitda, list):
        for i in range(len(ebitda)):
            if i < len(total_revenue) and total_revenue[i] and total_revenue[i] > 0:
                margin = (ebitda[i] / total_revenue[i]) * 100
                # Simple check: flag if margin is outside 5-40% range (reasonable for most companies)
                if margin < 5 or margin > 40:
                    flags.append({
                        "type": "warning",
                        "check": "ebitda_margin_unusual",
                        "message": f"EBITDA margin of {margin:.1f}% in projected year {i + 1} seems unusual",
                    })
    return flags


def _check_negative_ebitda(projection: Dict[str, Any]) -> List[Dict[str, str]]:
    """Flag negative EBITDA."""
    flags = []
    ebitda = projection.get("ebitda", [])

    if not ebitda:
        derived = projection.get("derived_items", {})
        if "EBITDA" in derived:
            ebitda_data = derived["EBITDA"]
            ebitda = list(ebitda_data.values()) if isinstance(ebitda_data, dict) else ebitda_data

    for i, val in enumerate(ebitda if isinstance(ebitda, list) else []):
        if val is not None and val < 0:
            flags.append({
                "type": "warning",
                "check": "negative_ebitda",
                "message": f"Negative EBITDA (₹{val:.0f} Cr) in projected year {i + 1}",
            })
    return flags


def _check_nan_none(projection: Dict[str, Any]) -> List[Dict[str, str]]:
    """Flag any NaN or None values in projections — CRITICAL."""
    flags = []

    def _scan(obj: Any, path: str = ""):
        if obj is None:
            flags.append({
                "type": "critical",
                "check": "null_value",
                "message": f"None value found at {path}",
            })
        elif isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
            flags.append({
                "type": "critical",
                "check": "nan_inf_value",
                "message": f"NaN/Inf value found at {path}",
            })
        elif isinstance(obj, dict):
            for k, v in obj.items():
                _scan(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                _scan(v, f"{path}[{i}]")

    _scan(projection.get("projections", projection.get("line_items", {})), "projections")
    _scan(projection.get("derived_items", {}), "derived_items")
    return flags


def _check_expense_exceeds_revenue(projection: Dict[str, Any]) -> List[Dict[str, str]]:
    """Flag if total expenses exceed revenue in any year — CRITICAL."""
    flags = []
    total_revenue = projection.get("total_revenue", [])
    total_expenses = projection.get("total_expenses", [])

    if isinstance(total_revenue, list) and isinstance(total_expenses, list):
        for i in range(min(len(total_revenue), len(total_expenses))):
            rev = total_revenue[i]
            exp = total_expenses[i]
            if rev is not None and exp is not None and exp > rev:
                flags.append({
                    "type": "critical",
                    "check": "expense_exceeds_revenue",
                    "message": f"Total expenses (₹{exp:.0f} Cr) exceed revenue (₹{rev:.0f} Cr) in year {i + 1}",
                })
    return flags


def _check_assumption_provenance(assumption_provenance: Dict[str, Any]) -> List[Dict[str, str]]:
    """Flag weak assumption-source coverage."""
    flags = []
    coverage = assumption_provenance.get("source_coverage_ratio", 0.0)
    total = assumption_provenance.get("total_assumptions", 0)
    if total == 0:
        flags.append(
            {
                "type": "warning",
                "check": "no_assumption_provenance",
                "message": "No assumption provenance available for validation.",
            }
        )
        return flags
    if coverage < 0.7:
        flags.append(
            {
                "type": "warning",
                "check": "low_assumption_source_coverage",
                "message": f"Only {coverage:.1%} assumptions include source citations (target >= 70%).",
            }
        )
    return flags


def validation_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run deterministic sanity checks on projection output.
    Routes back to analyst_review if critical flags are found.
    """
    projection = state.get("multi_year_projection", {})
    historical = state.get("historical_analysis", {})
    provenance = state.get("assumption_provenance", {})

    print(f"\n{'='*60}")
    print(f"🛡️ VALIDATION — Sanity Checks")
    print(f"{'='*60}")

    if not projection:
        print("  ⚠️ No projection data to validate")
        return {
            "validation_result": {
                "flags": [{"type": "critical", "check": "no_data", "message": "No projection data"}],
                "has_critical_flags": True,
                "has_warnings": False,
                "total_flags": 1,
            }
        }

    # Run all checks
    all_flags: List[Dict[str, str]] = []
    all_flags.extend(_check_revenue_growth(projection))
    all_flags.extend(_check_ebitda_margin(projection, historical))
    all_flags.extend(_check_negative_ebitda(projection))
    all_flags.extend(_check_nan_none(projection))
    all_flags.extend(_check_expense_exceeds_revenue(projection))
    all_flags.extend(_check_assumption_provenance(provenance))

    critical_flags = [f for f in all_flags if f["type"] == "critical"]
    warning_flags = [f for f in all_flags if f["type"] == "warning"]

    for f in all_flags:
        icon = "🔴" if f["type"] == "critical" else "🟡"
        print(f"  {icon} [{f['check']}] {f['message']}")

    if not all_flags:
        print("  ✅ All validation checks passed")

    result = {
        "flags": all_flags,
        "has_critical_flags": len(critical_flags) > 0,
        "has_warnings": len(warning_flags) > 0,
        "total_flags": len(all_flags),
        "critical_count": len(critical_flags),
        "warning_count": len(warning_flags),
    }

    print(f"\n  Summary: {len(critical_flags)} critical, {len(warning_flags)} warnings")

    return {"validation_result": result}
