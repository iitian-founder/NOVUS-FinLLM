from langchain_core.messages import HumanMessage
from projections.state import ProjectionState
from projections.materiality import identify_material_segments, identify_material_expenses

def orchestrator_node(state: ProjectionState):
    """
    The initial node that analyzes the raw Prowess financial data to identify
    material segments (>5%) and material expenses (>20%).
    Outputs a plan to the LLM context and sets the parallel router variables.
    """
    financial_data = state.get("financial_data", {})
    company_name = state.get("company_name", "Unknown Company")
    
    # Deterministic Materiality Checks
    material_segments = identify_material_segments(financial_data, threshold=0.05)
    material_expenses = identify_material_expenses(financial_data, revenue_threshold=0.20)
    
    # In a full flow, you would invoke an LLM here with the ORCHESTRATOR_PROMPT
    # to add qualitative analysis to the messages log.
    
    plan_message = (
        f"Orchestration complete for {company_name}.\n"
        f"Identified {len(material_segments)} material segments: {', '.join(material_segments)}.\n"
        f"Identified {len(material_expenses)} material expenses: {', '.join(material_expenses)}."
    )
    
    return {
        "messages": [HumanMessage(content=plan_message)],
        "material_segments": material_segments,
        "material_line_items": material_expenses
    }
