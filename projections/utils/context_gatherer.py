"""
Context Gatherer Utilities
==========================
Reusable tools for executing parallel search tasks and pruning context.
Used to assemble research contexts safely without exceeding LLM token limits.
"""

import asyncio
from tools.search_tools import tavily_broad_search
from tools.rag_tools import search_company_documents


# ── Context pruning config ───────────────────────────────────────────────────
MAX_CONTEXT_CHARS_PER_SOURCE = 3000
MAX_TOTAL_CONTEXT_CHARS      = 8000  # accommodates I&E plus text


def prune_context(raw_text: str, max_chars: int = MAX_CONTEXT_CHARS_PER_SOURCE) -> str:
    """Truncate and clean retrieved context to prevent context overflow."""
    if not raw_text:
        return ""

    # Remove excessive whitespace / blank lines
    lines = raw_text.strip().split("\n")
    cleaned_lines = [line.strip() for line in lines if line.strip()]
    cleaned = "\n".join(cleaned_lines)

    # Truncate if too long
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars] + "\n\n[... context truncated for brevity ...]"

    return cleaned


async def gather_context_async(
    company_name: str,
    ticker: str | None = None,
) -> tuple[str, str]:
    """
    Run Tavily web search and RAG retrieval in PARALLEL via asyncio.gather.
    Returns (tavily_result, rag_result) as pruned strings.

    This is broadly applicable across various pipeline branches wanting basic
    company background information.
    """
    search_query = f"{company_name} business model revenue segments overview"
    rag_ticker = ticker or company_name

    async def _tavily() -> str:
        try:
            result = await tavily_broad_search.ainvoke(
                {"query": search_query, "limit": 5}
            )
            return prune_context(str(result), MAX_CONTEXT_CHARS_PER_SOURCE)
        except Exception as exc:
            return f"[Tavily search failed: {exc}]"

    async def _rag() -> str:
        try:
            result = await search_company_documents.ainvoke(
                {
                    "query_text": (
                        f"What does {company_name} do? "
                        f"Business model, revenue segments, key products and services."
                    ),
                    "ticker": rag_ticker,
                    "agent_context": "initial business model research",
                }
            )
            return prune_context(str(result), MAX_CONTEXT_CHARS_PER_SOURCE)
        except Exception as exc:
            return f"[RAG query failed: {exc}]"

    # Run both in parallel — cuts context-gathering latency roughly in half
    tavily_result, rag_result = await asyncio.gather(_tavily(), _rag())
    return tavily_result, rag_result
