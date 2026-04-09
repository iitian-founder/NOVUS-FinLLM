"""
Context Gatherer Utilities (v2)
================================
Reusable tools for executing parallel search tasks and pruning context.
Used to assemble research contexts safely without exceeding LLM token limits.

v2 additions:
  - Firecrawl scraping fallback for segment data / financial reports
  - Multi-query RAG search (targeted queries for different data types)
  - Source citation tracking
"""

import asyncio
from typing import Optional
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


# ══════════════════════════════════════════════════════════════════════════════
# v2 ADDITIONS: Targeted research + Firecrawl fallback
# ══════════════════════════════════════════════════════════════════════════════

async def search_rag_targeted(
    company_name: str,
    query: str,
    ticker: str | None = None,
    max_chars: int = 2000,
) -> tuple[str, str]:
    """
    Run a targeted RAG search and return (result_text, source).
    The source string tracks where the data came from for citation.

    Returns
    -------
    tuple[str, str]
        (pruned_result_text, source_tag)
        source_tag is "rag" if RAG returned data, or "" if it failed.
    """
    rag_ticker = ticker or company_name
    try:
        result = await search_company_documents.ainvoke({
            "query_text": query,
            "ticker": rag_ticker,
            "agent_context": f"researching: {query[:80]}",
        })
        text = prune_context(str(result), max_chars)
        if text and len(text) > 50:
            return text, "rag"
    except Exception:
        pass
    return "", ""


async def search_tavily_targeted(
    query: str,
    max_chars: int = 2000,
    limit: int = 3,
) -> tuple[str, str]:
    """
    Run a targeted Tavily web search and return (result_text, source_url).
    """
    try:
        result = await tavily_broad_search.ainvoke({"query": query, "limit": limit})
        text = prune_context(str(result), max_chars)
        if text and len(text) > 50:
            return text, "tavily_search"
    except Exception:
        pass
    return "", ""


async def scrape_firecrawl(
    url: str,
    max_chars: int = 3000,
) -> tuple[str, str]:
    """
    Scrape a URL using Firecrawl as a fallback when RAG and Tavily fail.
    Returns (scraped_text, source_url).

    This is the last resort in the data fallback chain:
        Prowess CMIE → RAG → Tavily → Firecrawl
    """
    try:
        from tools.search_tools import firecrawl_scrape_url
        result = await firecrawl_scrape_url.ainvoke({"url": url})
        text = prune_context(str(result), max_chars)
        if text and len(text) > 50:
            return text, url
    except ImportError:
        # firecrawl tool not available
        return "", ""
    except Exception:
        return "", ""
    return "", ""


async def gather_with_fallback(
    company_name: str,
    query: str,
    ticker: str | None = None,
    firecrawl_url: Optional[str] = None,
) -> tuple[str, str]:
    """
    Execute the 3-tier search fallback chain:
        1. RAG (first choice — uses indexed company documents)
        2. Tavily web search (if RAG is empty)
        3. Firecrawl scrape (if both fail and a URL is provided)

    Returns (result_text, source_tag) where source_tag indicates provenance.
    """
    # Tier 1: RAG
    text, source = await search_rag_targeted(company_name, query, ticker)
    if text:
        return text, source

    # Tier 2: Tavily
    text, source = await search_tavily_targeted(f"{company_name} {query}")
    if text:
        return text, source

    # Tier 3: Firecrawl (if URL provided)
    if firecrawl_url:
        text, source = await scrape_firecrawl(firecrawl_url)
        if text:
            return text, source

    return "", "no_data"
