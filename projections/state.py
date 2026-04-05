"""
state.py — Financial Projections Pipeline State
=================================================
Central state definition for the LangGraph projections pipeline (v2).

Supports:
  - Parallel execution via Send API (segment researchers, expense analyzers)
  - Management guidance verification layer
  - Analyst-in-the-loop (HITL) interactive review via interrupt()
  - LLM-generated code execution in sandbox
  - Full P&L waterfall: Revenue → EBITDA → D&A → EBIT → Interest → PBT → Tax → PAT → EPS
"""

from typing import TypedDict, Annotated, List, Dict, Any, Optional
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


def merge_dict(a: Dict, b: Dict) -> Dict:
    """
    Custom reducer to merge dictionaries from parallel branches.
    Will overwrite existing keys if they overlap, but parallel segments
    should use unique keys (e.g. the segment name).
    """
    result = {**(a or {})}
    if b:
        result.update(b)
    return result


class ProjectionState(TypedDict):
    """
    The main LangGraph state for the Financial Projections Agent (v2).

    Organized by pipeline phase:
      Phase A: Autonomous research (no human input)
      Phase B: Interactive analyst loop (HITL via interrupt())
      Phase C: Projection computation + report generation
    """
    # ═══════════════════════════════════════════════════════════════════════
    # CORE
    # ═══════════════════════════════════════════════════════════════════════
    messages: Annotated[list[BaseMessage], add_messages]
    company_name: str
    financial_data: Dict[str, Any]                       # Parsed I&E data

    # ═══════════════════════════════════════════════════════════════════════
    # UPSTREAM CONTEXT (optional — from CIO pipeline)
    # ═══════════════════════════════════════════════════════════════════════
    executive_summary: Optional[str]                     # CIO PM Synthesis summary
    income_expenditure_psv: Optional[str]                # Cleaned I&E PSV string

    # ═══════════════════════════════════════════════════════════════════════
    # CMIE DATA (fetched by orchestrator — for below-the-line projections)
    # ═══════════════════════════════════════════════════════════════════════
    balance_sheet_data: Optional[str]                    # Balance_Sheet_Summary PSV
    capex_data: Optional[str]                            # Capital_Expenditure_Projects PSV
    capital_history_data: Optional[str]                  # Capital_History_Summary PSV
    cash_flow_data: Optional[str]                        # Cash_Flow PSV

    # ═══════════════════════════════════════════════════════════════════════
    # PHASE A — Autonomous Research Outputs
    # ═══════════════════════════════════════════════════════════════════════

    # Node 1: company_overview
    business_model_context: Optional[Dict[str, Any]]     # Structured CompanyOverviewSchema

    # Node 2: orchestrator
    material_segments: List[str]                          # Revenue segments > 10% threshold
    material_line_items: List[str]                        # Expense items > 10% threshold

    # Node 3: segment_researcher (parallel via Send API)
    segment_results: Annotated[Dict[str, Any], merge_dict]

    # Node 4: expense_analyzer (parallel via Send API)
    expense_results: Annotated[Dict[str, Any], merge_dict]

    # Node 5a: mgmt_guidance_extractor (parallel)
    mgmt_guidance: Dict[str, Any]                        # NarrativeDecoder output

    # Node 5b: historical_trends
    historical_analysis: Dict[str, Any]                  # Multi-year trends + CAGRs

    # Node 6a: assumptions_generator
    draft_assumptions: Dict[str, Any]                    # AssumptionsPackage (serialized)

    # Node 6b: guidance_deviation_check
    deviation_flags: Dict[str, Any]                      # Comparison: assumptions vs guidance

    # ═══════════════════════════════════════════════════════════════════════
    # PHASE B — Interactive Analyst Loop (HITL)
    # ═══════════════════════════════════════════════════════════════════════
    analyst_action: Optional[str]                        # "approved", "ask_followup", "apply_tweaks", "horizon_changed"
    followup_question: Optional[str]                     # Current question from analyst
    qa_history: List[Dict[str, str]]                     # [{question, answer}, ...]
    assumption_tweaks: List[Dict[str, Any]]              # Analyst overrides
    locked_assumptions: Optional[Dict[str, Any]]         # Final approved assumptions

    # ═══════════════════════════════════════════════════════════════════════
    # PHASE C — Projection Engine Outputs
    # ═══════════════════════════════════════════════════════════════════════
    generated_projection_code: Optional[str]             # Node 10a: LLM-generated Python
    code_approved: bool                                  # Node 10b: analyst approved the code
    code_execution_error: Optional[str]                  # Node 10c: sandbox error (if any)
    multi_year_projection: Dict[str, Any]                # Node 10c: executed projection results

    # ═══════════════════════════════════════════════════════════════════════
    # VALIDATION & REPORT
    # ═══════════════════════════════════════════════════════════════════════
    validation_result: Dict[str, Any]                    # Node 11: guardrail flags
    final_report: str                                    # Node 12: markdown report
