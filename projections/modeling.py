"""
modeling.py
===========
Deterministic helpers for scenarios, backtesting, and assumption provenance.
"""

from __future__ import annotations

from typing import Any, Dict, List


def _iter_assumptions(package: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    out.extend(package.get("revenue_assumptions", []))
    out.extend(package.get("expense_assumptions", []))
    out.extend(package.get("other_assumptions", []))
    return [a for a in out if isinstance(a, dict)]


def build_assumption_provenance(package: Dict[str, Any]) -> Dict[str, Any]:
    assumptions = _iter_assumptions(package)
    items = []
    with_source = 0
    for a in assumptions:
        src = a.get("source_urls") or []
        has_source = bool(src)
        with_source += 1 if has_source else 0
        items.append(
            {
                "line_item": a.get("line_item", "unknown"),
                "category": a.get("category", "unknown"),
                "projection_method": a.get("projection_method", "unknown"),
                "source_urls": src,
                "reasoning": a.get("reasoning", ""),
                "is_analyst_overridden": bool(a.get("is_analyst_overridden", False)),
                "confidence": a.get("confidence"),
            }
        )
    total = len(items)
    return {
        "items": items,
        "total_assumptions": total,
        "with_sources": with_source,
        "source_coverage_ratio": round((with_source / total), 3) if total else 0.0,
    }


def build_scenario_deltas(package: Dict[str, Any]) -> Dict[str, Any]:
    assumptions = _iter_assumptions(package)
    deltas = []
    for a in assumptions:
        growth = a.get("projected_growth_rate_pct")
        if isinstance(growth, (int, float)):
            deltas.append(
                {
                    "line_item": a.get("line_item", "unknown"),
                    "base_growth_pct": round(float(growth), 2),
                    "bull_growth_pct": round(float(growth) * 1.2, 2),
                    "bear_growth_pct": round(float(growth) * 0.8, 2),
                    "method": a.get("projection_method", "unknown"),
                }
            )
    return {
        "scenario_count": 3,
        "labels": ["bear", "base", "bull"],
        "line_item_deltas": deltas,
    }


def compute_backtest_metrics(historical_analysis: Dict[str, Any], package: Dict[str, Any]) -> Dict[str, Any]:
    """
    Lightweight backtest proxy:
    compares assumption historical_cagr_pct vs observed historical CAGR from analysis.
    """
    assumptions = _iter_assumptions(package)
    hist_cagrs = historical_analysis.get("cagrs", {}) if isinstance(historical_analysis, dict) else {}
    per_item = []
    abs_errors = []

    for a in assumptions:
        li = str(a.get("line_item", "")).strip()
        est_hist = a.get("historical_cagr_pct")
        observed = hist_cagrs.get(li) if isinstance(hist_cagrs, dict) else None
        if isinstance(est_hist, (int, float)) and isinstance(observed, (int, float)):
            err = abs(float(est_hist) - float(observed))
            abs_errors.append(err)
            per_item.append(
                {
                    "line_item": li,
                    "assumption_hist_cagr_pct": round(float(est_hist), 2),
                    "observed_hist_cagr_pct": round(float(observed), 2),
                    "abs_error_pct_points": round(err, 2),
                }
            )

    mape_proxy = round(sum(abs_errors) / len(abs_errors), 2) if abs_errors else None
    return {
        "items_evaluated": len(per_item),
        "mape_proxy_pct_points": mape_proxy,
        "per_item": per_item,
    }
