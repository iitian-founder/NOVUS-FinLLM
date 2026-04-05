from langgraph.types import Send
from projections.state import ProjectionState

def fan_out_to_segments(state: ProjectionState):
    """
    Reads the material_segments from the state and spins up a parallel
    'segment_researcher' node for each segment natively.
    """
    segments = state.get("material_segments", [])
    # Note: If this is an empty list, no segments are fanned out
    
    if not segments:
        # If no material segments were found, proceed directly to expenses (fallback logic)
        return "expense_analyzer"
        
    return [Send("segment_researcher", {"segment_name": s}) for s in segments]

def fan_out_to_expenses(state: ProjectionState):
    """
    Spins up a parallel 'expense_analyzer' node for each mapped expense item.
    """
    expenses = state.get("material_line_items", [])
    
    if not expenses:
        return "synthesizer"
        
    return [Send("expense_analyzer", {"expense_name": e}) for e in expenses]
