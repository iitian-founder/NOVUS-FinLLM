from typing import Dict, Any
from langchain_core.messages import HumanMessage
from projections.state import ProjectionState
from projections.tools_registry import RESEARCHER_TOOLS

def segment_researcher_node(state: ProjectionState) -> Dict[str, Any]:
    """
    Parallel Spoke Node: Researches a specific revenue segment using Search/News tools.
    Expects 'segment_name' to be passed directly in via the Send API state payload.
    """
    # Notice: Send API injects the payload directly over the state.
    segment = state.get("segment_name", "Unknown")
    
    # In a full flow, you bind an LLM to `RESEARCHER_TOOLS` and invoke it
    # to fetch AlphaVantage news and web search stats.
    # We simulate the LLM's output for the boilerplate.
    
    print(f"  [Segment] Researching: {segment}")
    
    # 1. Provide Context to Agent
    # 2. Agent invokes news_search_alpha_vantage(tickers="RELIANCE", topics=segment)
    # 3. Agent invokes web_search(query=f"{segment} sector outlook {company_name}")
    # 4. Agent returns qualitative projection drivers
    
    simulated_growth_projection = 0.12 # 12%
    
    # Accumulate into segment_results using merge_dict
    return {
        "segment_results": {
            segment: {
                "base_growth": simulated_growth_projection,
                "drivers": ["Strong consumer demand", "Favorable macros"]
            }
        }
    }
