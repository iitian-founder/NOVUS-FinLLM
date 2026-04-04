from langgraph.graph import StateGraph, START, END

# Import State
from projections.state import ProjectionState

# Import Nodes
from projections.nodes.orchestrator import orchestrator_node
from projections.nodes.segment_researcher import segment_researcher_node
from projections.nodes.expense_analyzer import expense_analyzer_node
from projections.nodes.synthesizer import synthesizer_node
from projections.nodes.blender import blender_node

# Import Edges
from projections.edges.routers import fan_out_to_segments, fan_out_to_expenses

def build_projections_graph():
    """
    Builds and compiles the Financial Projections Graph based on a map-reduce architecture.
    """
    builder = StateGraph(ProjectionState)

    # Add all nodes
    builder.add_node("orchestrator", orchestrator_node)
    builder.add_node("segment_researcher", segment_researcher_node)
    builder.add_node("expense_analyzer", expense_analyzer_node)
    builder.add_node("synthesizer", synthesizer_node)
    builder.add_node("blender", blender_node)

    # 1. Start -> Orchestrator
    builder.add_edge(START, "orchestrator")

    # 2. Orchestrator -> [Segment Researchers] (Map-Reduce Send API)
    builder.add_conditional_edges(
        "orchestrator",
        fan_out_to_segments,
        ["segment_researcher", "expense_analyzer"] # explicit fallback path
    )

    # 3. [Segment Researchers] -> Expense Analyzer fan-out logic
    # Note: After ALL segments finish, we route to expenses. We use conditional edges to route.
    builder.add_conditional_edges(
        "segment_researcher",
        fan_out_to_expenses,
        ["expense_analyzer", "synthesizer"] # explicit fallback path
    )
    
    # 4. [Expense Analyzers] -> Synthesizer
    # When all expense analyzers complete, they converge into the synthesizer
    builder.add_edge("expense_analyzer", "synthesizer")
    
    # 5. Synthesizer -> Blender (Mgmt Guidance)
    builder.add_edge("synthesizer", "blender")
    
    # 6. Blender -> End
    builder.add_edge("blender", END)

    # Compile and return
    return builder.compile()

if __name__ == "__main__":
    app = build_projections_graph()
    print("Financial Projections Graph compiled successfully.")
