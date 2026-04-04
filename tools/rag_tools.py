from langchain_core.tools import tool
from typing import Optional
import sys
from pathlib import Path

# Provide access to root modules
base_dir = Path(__file__).resolve().parent.parent
if str(base_dir) not in sys.path:
    sys.path.append(str(base_dir))

from rag_engine import get_context_for_agent

@tool
def search_company_documents(query_text: str, ticker: str, agent_context: Optional[str] = None) -> str:
    """
    Query the internal RAG database for specific company information.
    
    Args:
        query_text: Information to search for in company filings and transcripts.
        ticker: The ticker symbol of the company (e.g. 'RELIANCE.NS').
        agent_context: Optional string providing context on why the agent is asking this.
    """
    try:
        # Wrap the rag_engine method
        result = get_context_for_agent(
            query=query_text,
            ticker=ticker,
            top_k=5, 
            agent_context=agent_context or 'Projections Data Gathering'
        )
        return result
    except Exception as e:
        return f"RAG Query Failed: {str(e)}"
