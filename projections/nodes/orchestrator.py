"""
Orchestrator Node
=================
Analyzes raw financial data to identify material segments and expenses.
Sets up the plan for parallel research via the Send API.

v2: Now enriches financial_data from Prowess I&E PSV (if available in state)
    before running materiality checks, so that real expense line items from
    CMIE are used for thresholding instead of empty stubs.
"""

from langchain_core.messages import HumanMessage
from projections.state import ProjectionState
from projections.materiality import (
    identify_material_segments,
    identify_material_expenses,
    enrich_financial_data_from_psv,
)


def orchestrator_node(state: ProjectionState):
    """
    The orchestration node that:
      1. Enriches financial_data with parsed I&E PSV (if available).
      2. Runs deterministic materiality checks (segments > 5%, expenses > 20%).
      3. Sets parallel router variables for downstream map-reduce.
    """
    financial_data = state.get("financial_data", {})
    company_name = state.get("company_name", "Unknown Company")
    ie_psv = state.get("income_expenditure_psv")

    # ── Enrich financial_data from Prowess I&E PSV ───────────────────────
    if ie_psv:
        print("\n📊 Orchestrator: Enriching financial_data from Prowess I&E PSV...")
        financial_data = enrich_financial_data_from_psv(financial_data, ie_psv)
        print(f"   Total Revenue: {financial_data.get('total_revenue', 'N/A')}")
        print(f"   Expense items: {len(financial_data.get('expenses', {}))}")
    
    # ── Deterministic Materiality Checks ─────────────────────────────────
    material_segments = identify_material_segments(financial_data, threshold=0.05)
    material_expenses = identify_material_expenses(financial_data, revenue_threshold=0.20)
    
    plan_message = (
        f"Orchestration complete for {company_name}.\n"
        f"Identified {len(material_segments)} material segments: {', '.join(material_segments) if material_segments else 'None (segment data not in I&E — will use company_overview segments)'}.\n"
        f"Identified {len(material_expenses)} material expenses: {', '.join(material_expenses) if material_expenses else 'None found above threshold'}."
    )

    print(f"\n{'='*60}")
    print(f"📋 ORCHESTRATOR NODE — {company_name}")
    print(f"{'='*60}")
    print(plan_message)
    
    return {
        "messages": [HumanMessage(content=plan_message)],
        "material_segments": material_segments,
        "material_line_items": material_expenses,
        "financial_data": financial_data,  # pass back enriched data
    }
