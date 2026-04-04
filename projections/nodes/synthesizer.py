from typing import Dict, Any
from langchain_core.messages import HumanMessage
from projections.state import ProjectionState
from projections.tools_registry import SYNTHESIZER_TOOLS

def synthesizer_node(state: ProjectionState) -> Dict[str, Any]:
    """
    Takes all accumulated results from segment and expense researches and
    forces structured Python computations to arrive at numerical projections.
    """
    segments = state.get("segment_results", {})
    expenses = state.get("expense_results", {})
    
    print(f"Synthesizer collecting {len(segments)} segments and {len(expenses)} expenses.")
    
    # 1. Synthesizer uses `project_future_value` math_tool for Revenue
    bottom_up_revenue = 15000.0 * 1.12 # Simplified example
    
    # 2. Synthesizer uses `calculate_margin` to find EBITDA
    bottom_up_expenses = bottom_up_revenue * 0.18
    bottom_up_ebitda = bottom_up_revenue - bottom_up_expenses
    
    projection = {
        "revenue_forecast": bottom_up_revenue,
        "ebitda_forecast": bottom_up_ebitda
    }
    
    message = f"Synthesized Bottom-Up Projection:\n{projection}"
    
    return {
        "bottom_up_projection": projection,
        "messages": [HumanMessage(content=message)]
    }
