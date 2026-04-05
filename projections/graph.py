"""
graph.py — Financial Projections Graph (v2)
============================================
Builds and compiles the LangGraph for the full projection pipeline.

Architecture:
  Phase A (Autonomous): company_overview → orchestrator → [parallel research] → historical_trends → assumptions_generator → guidance_deviation_check
  Phase B (Interactive): analyst_review ⇄ followup_qa / apply_tweaks
  Phase C (Projection):  code_generator → code_review → code_executor → validation → report_generator

Requires a checkpointer for interrupt() support (MemorySaver for dev, SqliteSaver for prod).
"""

from langgraph.graph import StateGraph, START, END

# Import State
from projections.state import ProjectionState

# Import Nodes — Phase A (Autonomous Research)
from projections.nodes.company_overview import company_overview_node
from projections.nodes.orchestrator import orchestrator_node
from projections.nodes.segment_researcher import segment_researcher_node
from projections.nodes.expense_analyzer import expense_analyzer_node
from projections.nodes.mgmt_guidance_extractor import mgmt_guidance_extractor_node
from projections.nodes.historical_trends import historical_trends_node
from projections.nodes.assumptions_generator import assumptions_generator_node
from projections.nodes.guidance_deviation_check import guidance_deviation_check_node

# Import Nodes — Phase B (Interactive Analyst Loop)
from projections.nodes.analyst_review import analyst_review_node
from projections.nodes.followup_qa import followup_qa_node
from projections.nodes.apply_tweaks import apply_tweaks_node

# Import Nodes — Phase C (Projection Engine)
from projections.nodes.code_generator import code_generator_node
from projections.nodes.code_review import code_review_node
from projections.nodes.code_executor import code_executor_node
from projections.nodes.validation import validation_node
from projections.nodes.report_generator import report_generator_node

# Import Edge Routers
from projections.edges.routers import (
    fan_out_to_parallel,
    analyst_action_router,
    code_review_router,
    validation_router,
)


def build_projections_graph(checkpointer=None):
    """
    Builds and compiles the Financial Projections Graph (v2).

    Parameters
    ----------
    checkpointer : optional
        A LangGraph checkpointer for interrupt/resume support.
        Use MemorySaver() for development, SqliteSaver for production.
        Required for the HITL (interrupt()) workflow to function.

    Returns
    -------
    CompiledGraph
        The compiled LangGraph ready for invocation.
    """
    builder = StateGraph(ProjectionState)

    # ═══════════════════════════════════════════════════════════════════════
    # ADD NODES
    # ═══════════════════════════════════════════════════════════════════════

    # Phase A: Autonomous Research
    builder.add_node("company_overview", company_overview_node)
    builder.add_node("orchestrator", orchestrator_node)
    builder.add_node("segment_researcher", segment_researcher_node)
    builder.add_node("expense_analyzer", expense_analyzer_node)
    builder.add_node("mgmt_guidance_extractor", mgmt_guidance_extractor_node)
    builder.add_node("historical_trends", historical_trends_node)
    builder.add_node("assumptions_generator", assumptions_generator_node)
    builder.add_node("guidance_deviation_check", guidance_deviation_check_node)

    # Phase B: Interactive Analyst Loop
    builder.add_node("analyst_review", analyst_review_node)
    builder.add_node("followup_qa", followup_qa_node)
    builder.add_node("apply_tweaks", apply_tweaks_node)

    # Phase C: Projection Engine
    builder.add_node("code_generator", code_generator_node)
    builder.add_node("code_review", code_review_node)
    builder.add_node("code_executor", code_executor_node)
    builder.add_node("validation", validation_node)
    builder.add_node("report_generator", report_generator_node)

    # ═══════════════════════════════════════════════════════════════════════
    # ADD EDGES
    # ═══════════════════════════════════════════════════════════════════════

    # Phase A: Linear start
    builder.add_edge(START, "company_overview")
    builder.add_edge("company_overview", "orchestrator")

    # Phase A: Fan-out to parallel research (segments + expenses + mgmt guidance)
    builder.add_conditional_edges(
        "orchestrator",
        fan_out_to_parallel,
        ["segment_researcher", "expense_analyzer", "mgmt_guidance_extractor", "historical_trends"],
    )

    # Phase A: All parallel branches converge → historical_trends
    builder.add_edge("segment_researcher", "historical_trends")
    builder.add_edge("expense_analyzer", "historical_trends")
    builder.add_edge("mgmt_guidance_extractor", "historical_trends")

    # Phase A: historical_trends → assumptions_generator → guidance_deviation_check
    builder.add_edge("historical_trends", "assumptions_generator")
    builder.add_edge("assumptions_generator", "guidance_deviation_check")
    builder.add_edge("guidance_deviation_check", "analyst_review")

    # Phase B: Analyst review → conditional routing
    builder.add_conditional_edges(
        "analyst_review",
        analyst_action_router,
        ["code_generator", "followup_qa", "apply_tweaks", "analyst_review"],
    )
    builder.add_edge("followup_qa", "analyst_review")
    builder.add_edge("apply_tweaks", "analyst_review")

    # Phase C: Code generation → review → execution
    builder.add_edge("code_generator", "code_review")
    builder.add_conditional_edges(
        "code_review",
        code_review_router,
        ["code_executor", "code_generator"],
    )
    builder.add_edge("code_executor", "validation")

    # Phase C: Validation → report or back to analyst
    builder.add_conditional_edges(
        "validation",
        validation_router,
        ["report_generator", "analyst_review"],
    )
    builder.add_edge("report_generator", END)

    # ═══════════════════════════════════════════════════════════════════════
    # COMPILE
    # ═══════════════════════════════════════════════════════════════════════
    compile_kwargs = {}
    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer

    return builder.compile(**compile_kwargs)


if __name__ == "__main__":
    # Quick build test (no checkpointer = no interrupt support)
    app = build_projections_graph()
    print("✅ Financial Projections Graph v2 compiled successfully.")
    print(f"   Nodes: {list(app.nodes.keys())}")
