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
    The main LangGraph state for the Financial Projections Agent.
    Supports parallel execution via the Send API.
    """
    # Core state
    messages: Annotated[list[BaseMessage], add_messages]
    company_name: str
    business_model_context: Optional[Dict[str, Any]] # Structured overview from company_overview_node
    financial_data: Dict[str, Any]                   # Raw data from Prowess API
    
    # Pre-computed context from upstream CIO pipeline (optional)
    # When present, company_overview_node skips Tavily/RAG and uses these directly.
    executive_summary: Optional[str]                 # PM Synthesis executive summary from CIO report
    income_expenditure_psv: Optional[str]            # Cleaned I&E statement PSV from Prowess/clean_json
    
    # Hub and Spoke routing state - Revenue Sectors
    material_segments: List[str]                     # Segments > 5% threshold
    segment_results: Annotated[Dict[str, Any], merge_dict]  # Accumulated by segment_researcher nodes
    
    # Hub and Spoke routing state - Expense Items
    material_line_items: List[str]                   # Expense items > 20%
    expense_results: Annotated[Dict[str, Any], merge_dict]  # Accumulated by expense_analyzer nodes
    
    # Mathematical aggregations
    bottom_up_projection: Dict[str, float]
    mgmt_guidance_projection: Dict[str, float]
    final_projection: Dict[str, float]               # The mathematically blended final output
