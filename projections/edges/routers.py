"""
Edge Routers for the Financial Projections Graph (v2)
=====================================================
Routes that control the flow between nodes.

Key routers:
  - fan_out_to_parallel: Orchestrator → segment_researchers + expense_analyzers + mgmt_guidance (parallel)
  - analyst_action_router: Analyst review → next action based on analyst input
  - code_review_router: Code review → execute or regenerate
  - validation_router: Validation → report or back to analyst
"""

from langgraph.types import Send
from projections.state import ProjectionState


# ══════════════════════════════════════════════════════════════════════════════
# PHASE A: Research fan-out
# ══════════════════════════════════════════════════════════════════════════════

def fan_out_to_parallel(state: ProjectionState):
    """
    Fan-out from orchestrator → parallel research branches.

    Sends:
      1. One segment_researcher per material segment (via Send API)
      2. One expense_analyzer per material expense item (via Send API)
      3. One mgmt_guidance_extractor (single node, runs in parallel)
    """
    sends = []

    # Segment researchers (parallel)
    segments = state.get("material_segments", [])
    for s in segments:
        sends.append(Send("segment_researcher", {
            "segment_name": s,
            "company_name": state["company_name"],
            "financial_data": state.get("financial_data", {}),
        }))

    # Expense analyzers (parallel)
    expenses = state.get("material_line_items", [])
    for e in expenses:
        sends.append(Send("expense_analyzer", {
            "expense_name": e,
            "company_name": state["company_name"],
            "financial_data": state.get("financial_data", {}),
        }))

    # Management guidance extractor (single node, also parallel)
    sends.append(Send("mgmt_guidance_extractor", {
        "company_name": state["company_name"],
        "business_model_context": state.get("business_model_context", {}),
    }))

    if not sends:
        # Safety: if no segments/expenses and guidance extractor fails,
        # proceed directly to historical_trends
        return "historical_trends"

    return sends


# ══════════════════════════════════════════════════════════════════════════════
# PHASE B: Interactive loop routers
# ══════════════════════════════════════════════════════════════════════════════

def analyst_action_router(state: ProjectionState):
    """
    Routes from analyst_review based on the analyst's chosen action.
    """
    action = state.get("analyst_action")

    if action == "approved":
        return "code_generator"
    elif action == "ask_followup":
        return "followup_qa"
    elif action == "apply_tweaks":
        return "apply_tweaks"
    elif action == "horizon_changed":
        return "analyst_review"  # re-present with updated horizon
    return "analyst_review"  # default: loop back


def code_review_router(state: ProjectionState):
    """
    Routes from code_review based on analyst's approval of generated code.
    """
    if state.get("code_approved"):
        return "code_executor"
    return "code_generator"  # regenerate


# ══════════════════════════════════════════════════════════════════════════════
# PHASE C: Validation router
# ══════════════════════════════════════════════════════════════════════════════

def validation_router(state: ProjectionState):
    """
    Routes from validation: pass → report, fail → back to analyst for fixes.
    """
    result = state.get("validation_result", {})
    if result.get("has_critical_flags"):
        return "analyst_review"  # show warnings, let analyst fix assumptions
    return "report_generator"
