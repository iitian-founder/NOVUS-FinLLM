from typing import Dict, Any
from langchain_core.messages import HumanMessage
from projections.state import ProjectionState
from projections.tools_registry import RESEARCHER_TOOLS

def expense_analyzer_node(state: ProjectionState) -> Dict[str, Any]:
    """
    Parallel Spoke Node: Researches a specific material expense item using Search/News tools.
    """
    expense = state.get("expense_name", "Unknown Expense")
    
    print(f"  [Expense] Analyzing: {expense}")
    
    # Analyze cost drivers using RESEARCHER_TOOLS
    simulated_margin_assumption = 0.18 # Projecting an 18% margin for this expense against revenue
    
    # Accumulate into expense_results using merge_dict
    return {
        "expense_results": {
            expense: {
                "projected_margin": simulated_margin_assumption,
                "drivers": ["Supply chain normalization", "Commodity price cooling"]
            }
        }
    }
