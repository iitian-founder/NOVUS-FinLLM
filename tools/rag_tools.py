from langchain_core.tools import tool
from typing import Optional
import sys
from pathlib import Path

# Provide access to root modules
base_dir = Path(__file__).resolve().parent.parent
if str(base_dir) not in sys.path:
    sys.path.append(str(base_dir))

from rag_engine import query as rag_query

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
        results = rag_query(
            ticker=ticker,
            question=query_text,
            top_k=5,
        )

        if not results:
            return f"No relevant documents found in RAG store for ticker '{ticker}'."

        context_parts = [f"--- RAG CONTEXT [{agent_context or 'Query'}] ---\n"]
        for i, r in enumerate(results, 1):
            meta = r.get("metadata", {})
            source = (
                f"[Source: {meta.get('filename', '?')} | "
                f"{meta.get('doc_type', '?')} | "
                f"Section: {meta.get('section', '?')} | "
                f"Relevance: {r.get('relevance', '?')}]"
            )
            context_parts.append(f"**Chunk {i}** {source}")
            context_parts.append(r["text"][:1500])
            context_parts.append("")

        context_parts.append("--- END RAG CONTEXT ---")
        return "\n".join(context_parts)

    except Exception as e:
        return f"RAG Query Failed: {str(e)}"

