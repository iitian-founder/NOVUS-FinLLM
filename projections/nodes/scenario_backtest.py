"""
scenario_backtest.py
====================
Builds scenario deltas, backtest metrics, and assumption provenance.
"""

from __future__ import annotations

from typing import Any, Dict

from projections.modeling import (
    build_assumption_provenance,
    build_scenario_deltas,
    compute_backtest_metrics,
)


def scenario_backtest_node(state: Dict[str, Any]) -> Dict[str, Any]:
    assumptions = state.get("locked_assumptions") or state.get("draft_assumptions") or {}
    historical = state.get("historical_analysis") or {}

    scenario_analysis = build_scenario_deltas(assumptions)
    backtest_metrics = compute_backtest_metrics(historical, assumptions)
    assumption_provenance = build_assumption_provenance(assumptions)

    print(f"\n{'='*60}")
    print("📈 SCENARIO + BACKTEST")
    print(f"{'='*60}")
    print(
        f"  Scenarios: {scenario_analysis.get('scenario_count', 0)} | "
        f"Backtest items: {backtest_metrics.get('items_evaluated', 0)} | "
        f"Source coverage: {assumption_provenance.get('source_coverage_ratio', 0.0):.1%}"
    )

    return {
        "scenario_analysis": scenario_analysis,
        "backtest_metrics": backtest_metrics,
        "assumption_provenance": assumption_provenance,
    }
