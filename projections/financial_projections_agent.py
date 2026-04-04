import sys
from pathlib import Path
from langchain_core.messages import HumanMessage

# Add the parent directory to sys.path
base_dir = Path(__file__).resolve().parent.parent
if str(base_dir) not in sys.path:
    sys.path.append(str(base_dir))

from projections.graph import build_projections_graph

def run_projections(company_name: str, years: int = 3) -> dict:
    """
    Public API to execute the financial projections graph for a given company.
    
    Args:
        company_name: The company to project.
        years: How many years out to project.
        
    Returns:
        The final state dict containing the blended projection.
    """
    app = build_projections_graph()
    
    # Initialize the complex state
    initial_state = {
        "messages": [HumanMessage(content=f"Begin projections for {company_name}")],
        "company_name": company_name,
        "business_model_context": None, # Will be fetched via RAG later
        "financial_data": {
            # Simulated dummy data for the orchestrator to test the flow
            "total_revenue": 10000.0,
            "segments": {
                "Infrastructure": 4500.0,
                "Consumer_Goods": 2500.0,
                "Export": 2500.0,
                "Other": 500.0
            },
            "expenses": {
                "Raw_Materials": 3000.0,
                "Employee_Costs": 2500.0,
                "Other_Expenses": 500.0
            }
        },
        "material_segments": [],
        "segment_results": {},
        "material_line_items": [],
        "expense_results": {},
        "bottom_up_projection": {},
        "mgmt_guidance_projection": {},
        "final_projection": {}
    }
    
    print(f"--- Starting Financial Projections for {company_name} ---")
    final_state = app.invoke(initial_state)
    return final_state

if __name__ == "__main__":
    # Test execution
    result = run_projections(company_name="Reliance Industries Ltd")
    print("\n--- FINAL PROJECTION RESULT ---")
    print(result.get("final_projection"))
