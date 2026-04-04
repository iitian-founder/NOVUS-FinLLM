from typing import Dict, List, Any

def identify_material_segments(financial_data: Dict[str, Any], threshold: float = 0.05) -> List[str]:
    """
    Identifies revenue segments that contribute more than the threshold (default 5%)
    to the total revenue base, isolating them for parallel research analysis.
    
    Args:
        financial_data: The fetched Prowess API JSON structure.
        threshold: The fractional percentage threshold (0.05 = 5%).
    """
    # NOTE: This implementation depends heavily on the structure of the data returned by prowess.
    # Below is a stub structure anticipating standard segment decompositions.
    material = []
    
    # Safely extract segments, substituting with an empty dict if not found
    segments = financial_data.get("segments", {})
    total_revenue = financial_data.get("total_revenue", sum(segments.values()) if segments else 0)
    
    if total_revenue <= 0:
        return material
        
    for segment_name, segment_value in segments.items():
        if (segment_value / total_revenue) >= threshold:
            material.append(segment_name)
            
    return material

def identify_material_expenses(financial_data: Dict[str, Any], revenue_threshold: float = 0.20) -> List[str]:
    """
    Identifies expense line items that make up a significant portion of the total revenue
    (default 20%). This guides the model to only research the largest cost drivers.
    """
    material = []
    
    expenses = financial_data.get("expenses", {})
    total_revenue = financial_data.get("total_revenue", 1.0) # Avoid div-by-zero
    
    for expense_name, expense_value in expenses.items():
        if (expense_value / total_revenue) >= revenue_threshold:
            material.append(expense_name)
            
    return material

# PROMPTS
ORCHESTRATOR_PROMPT = """
You are the orchestrator for the Financial Projections Agent.
Based on the company data and business model, your job is to review the quantitative material
segments and expenses provided and set up the plan for deep research.
"""

SYNTHESIZER_PROMPT = """
You are the Synthesizer. You take the raw notes and numerical insights from the parallel segment
and expense researchers and format them into structured JSON mathematical inputs for the formula tools.
"""
