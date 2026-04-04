from typing import Dict, Any
from langchain_core.messages import HumanMessage
from projections.state import ProjectionState

# Note: In actual execution, we would import the management_quality logic directly
# from agents.narrative_decoder import extract_management_guidance

def blender_node(state: ProjectionState) -> Dict[str, Any]:
    """
    Final node that calls the narrative decoder agent and does a 70/30 weighting
    between management's historical guidance accuracy (70%) and our bottom-up research (30%).
    """
    bottom_up = state.get("bottom_up_projection", {})
    company_name = state.get("company_name", "Unknown Company")
    
    print(f"Blending predictions for {company_name}...")
    
    # 1. Call narrative decoder to get management qualitative/quantitative guidance
    # mgmt_guidance = extract_management_guidance(company_name, context)
    mgmt_guidance = {
        "revenue_forecast": 16000.0,
        "ebitda_forecast": 3200.0
    }
    
    # 2. Blend: 70% Mgmt / 30% Bottom-Up
    final_projection = {}
    for key in bottom_up:
        bu_val = bottom_up[key]
        mgmt_val = mgmt_guidance.get(key, bu_val) # Fallback to bottom-up if mgmt missing
        
        final_projection[key] = (0.7 * mgmt_val) + (0.3 * bu_val)
        
    message = f"Final Blended Forecast:\n{final_projection}"
    
    return {
        "mgmt_guidance_projection": mgmt_guidance,
        "final_projection": final_projection,
        "messages": [HumanMessage(content=message)]
    }
