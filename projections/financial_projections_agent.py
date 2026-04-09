"""
financial_projections_agent.py — v2 Public API
================================================
Entry point for the financial projections pipeline.
Supports both standalone mode and CIO-pipeline integration.

Requires a checkpointer for HITL (interrupt/resume) support.
"""

import sys
from pathlib import Path
from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage

# Add the parent directory to sys.path
base_dir = Path(__file__).resolve().parent.parent
if str(base_dir) not in sys.path:
    sys.path.append(str(base_dir))

from projections.graph import build_projections_graph


def run_projections(
    company_name: str,
    *,
    years: int = 3,
    executive_summary: Optional[str] = None,
    income_expenditure_psv: Optional[str] = None,
    checkpointer=None,
    thread_id: str = "default",
) -> Dict[str, Any]:
    """
    Public API to execute the financial projections graph (v2).

    Args:
        company_name: The company to project.
        years: Projection horizon (default 3).
        executive_summary: Optional CIO PM Synthesis summary (standalone mode skips this).
        income_expenditure_psv: Optional pre-fetched I&E PSV string.
        checkpointer: LangGraph checkpointer for interrupt/resume support.
            Use MemorySaver() for development.
        thread_id: Thread ID for the checkpointer.

    Returns:
        The final state dict (or intermediate state if interrupted for HITL).
    """
    app = build_projections_graph(checkpointer=checkpointer)

    initial_state = {
        "messages": [HumanMessage(content=f"Begin projections for {company_name}")],
        "company_name": company_name,
        "financial_data": {},
        # Upstream context (optional — from CIO pipeline)
        "executive_summary": executive_summary,
        "income_expenditure_psv": income_expenditure_psv,
        # Phase A outputs (will be populated by nodes)
        "business_model_context": None,
        "material_segments": [],
        "material_line_items": [],
        "segment_results": {},
        "expense_results": {},
        "mgmt_guidance": {},
        "historical_analysis": {},
        "draft_assumptions": {},
        "deviation_flags": {},
        "scenario_analysis": {},
        "backtest_metrics": {},
        "assumption_provenance": {},
        # Phase B (HITL)
        "analyst_action": None,
        "followup_question": None,
        "qa_history": [],
        "assumption_tweaks": [],
        "locked_assumptions": None,
        # Phase C (Projection)
        "generated_projection_code": None,
        "code_approved": False,
        "code_execution_error": None,
        "multi_year_projection": {},
        # Validation & Report
        "validation_result": {},
        "final_report": "",
        # CMIE data (fetched by orchestrator)
        "balance_sheet_data": None,
        "capex_data": None,
        "capital_history_data": None,
        "cash_flow_data": None,
    }

    print(f"\n{'='*70}")
    print(f"🚀 NOVUS Financial Projections v2 — {company_name}")
    print(f"   Horizon: {years} years | Mode: {'CIO Pipeline' if executive_summary else 'Standalone'}")
    print(f"{'='*70}")

    config = {"configurable": {"thread_id": thread_id}}
    final_state = app.invoke(initial_state, config=config)
    return final_state


if __name__ == "__main__":
    # Development test — standalone mode
    from langgraph.checkpoint.memory import MemorySaver

    checkpointer = MemorySaver()
    result = run_projections(
        company_name="Hindustan Unilever Ltd.",
        checkpointer=checkpointer,
    )
    print(f"\n{'='*70}")
    print("📊 FINAL STATE KEYS:")
    for k, v in result.items():
        if isinstance(v, str):
            print(f"  {k}: {len(v)} chars")
        elif isinstance(v, dict):
            print(f"  {k}: {len(v)} keys")
        elif isinstance(v, list):
            print(f"  {k}: {len(v)} items")
        else:
            print(f"  {k}: {type(v).__name__}")
