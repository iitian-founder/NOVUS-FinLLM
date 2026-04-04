import operator
from typing import TypedDict, Annotated, List, Dict, Any
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import StateGraph, END, START
from langgraph.graph.message import add_messages
from langgraph.types import Send

# 1. Custom reducer to merge dictionaries from parallel branches
def merge_dict(a: Dict, b: Dict) -> Dict:
    result = {**(a or {})}
    if b:
        # For this toy graph, if keys overlap we just overwrite
        # In reality, segments will have unique keys (their segment name)
        result.update(b)
    return result

# 2. Define the State
class ToyState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    material_segments: List[str]
    segment_results: Annotated[Dict[str, Any], merge_dict]

# 3. Define the Orchestrator Node
def orchestrator_node(state: ToyState):
    print("--- Orchestrator Node ---")
    print(f"Identifying material segments...")
    
    # Simulate finding material segments
    segments = ["Infrastructure", "Consumer_Goods", "Export"]
    
    return {
        "material_segments": segments,
        "messages": [HumanMessage(content=f"Found {len(segments)} segments to research.")]
    }

# 4. Define the Parallel Spoke Node
def segment_researcher_node(state: ToyState) -> Dict:
    # Notice how Send API passes the payload directly as the 'state' to this node.
    # We expect 'segment_name' to be passed in.
    segment = state.get("segment_name", "Unknown Segment")
    print(f"  [Parallel Spoke] Researching segment: {segment}...")
    
    # Simulate research and projection logic
    simulated_growth = 0.15 if segment == "Infrastructure" else 0.08
    
    return {
        # Using the merge_dict reducer, this dictionary gets merged into the global segment_results
        "segment_results": {
            segment: {
                "growth": simulated_growth,
                "notes": f"Simulated research for {segment}"
            }
        }
    }

# 5. Define the Aggregator Node
def synthesizer_node(state: ToyState):
    print("--- Synthesizer Node ---")
    results = state.get("segment_results", {})
    print(f"Gathered results from {len(results)} segments:")
    for k, v in results.items():
        print(f"  - {k}: {v}")
    
    # Simulate a final action
    return {"messages": [HumanMessage(content="Synthesis complete.")]}

# 6. Define the Routing Logic for Send API
def fan_out_to_segments(state: ToyState):
    segments = state.get("material_segments", [])
    print(f"Routing to {len(segments)} parallel researchers...")
    
    # Return a list of Send objects, representing the branches to create
    return [Send("segment_researcher", {"segment_name": s}) for s in segments]

# 7. Build the Graph
builder = StateGraph(ToyState)

builder.add_node("orchestrator", orchestrator_node)
builder.add_node("segment_researcher", segment_researcher_node)
builder.add_node("synthesizer", synthesizer_node)

builder.add_edge(START, "orchestrator")

# Fan-out: Orchestrator to Segment Researchers
builder.add_conditional_edges(
    "orchestrator",
    fan_out_to_segments,
    ["segment_researcher"]
)

# Fan-in: Segment Researchers to Synthesizer
builder.add_edge("segment_researcher", "synthesizer")
builder.add_edge("synthesizer", END)

# 8. Compile the Graph
app = builder.compile()

# Run the test
if __name__ == "__main__":
    print("Starting Toy Graph Execution...\n")
    initial_state = {
        "messages": [HumanMessage(content="Start projections routing test")],
        "material_segments": [],
        "segment_results": {}
    }
    
    final_state = app.invoke(initial_state)
    print("\n--- FINAL STATE ---")
    print(f"Segment Results object: {final_state['segment_results']}")
