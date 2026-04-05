"""
mgmt_guidance_extractor.py — Management Guidance Extraction Node
=================================================================
Queries RAG for forward-looking statements from concalls and uses
the NarrativeDecoderV3 to extract guidance, tone shifts, and dodges.

Role: VERIFICATION LAYER (not the base for assumptions).
Management guidance is compared against bottom-up assumptions to flag deviations.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from projections.utils.context_gatherer import prune_context


async def _extract_concall_guidance(company_name: str) -> str:
    """Query RAG for forward-looking statements from latest concalls."""
    from tools.rag_tools import search_company_documents

    queries = [
        f"{company_name} management guidance revenue growth outlook next year",
        f"{company_name} earnings call forward looking statements capex margin guidance",
        f"{company_name} concall Q&A management promises targets FY25 FY26",
    ]
    results = []
    for q in queries:
        try:
            r = await search_company_documents.ainvoke({
                "query_text": q,
                "ticker": company_name,
                "agent_context": "extracting management guidance",
            })
            results.append(prune_context(str(r), 2000))
        except Exception:
            pass
    return "\n\n".join(results)


async def mgmt_guidance_extractor_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract management guidance from concall transcripts via RAG + NarrativeDecoder.

    Runs in PARALLEL with segment_researcher and expense_analyzer.
    Output is used by guidance_deviation_check to flag assumption deviations.
    """
    company = state.get("company_name", "")
    print(f"\n{'='*60}")
    print(f"🎙️ MGMT GUIDANCE EXTRACTOR: {company}")
    print(f"{'='*60}")

    # Step 1: Get raw concall text from RAG
    concall_text = await _extract_concall_guidance(company)
    print(f"  📥 RAG concall text: {len(concall_text)} chars")

    guidance_output: Dict[str, Any] = {}

    # Step 2: If RAG has content, run NarrativeDecoder on it
    if concall_text and len(concall_text) > 100:
        try:
            from agents.narrative_decoder import NarrativeDecoderV3
            decoder = NarrativeDecoderV3()
            guidance_output = await decoder.run(
                doc=concall_text,
                tables={},
                ticker=company,
            )
            print("  ✅ NarrativeDecoder extraction complete")
        except Exception as exc:
            print(f"  ⚠️ NarrativeDecoder failed: {exc}")
            guidance_output = {"executive_summary": concall_text[:500], "source": "rag_raw"}
    else:
        # Fallback: search web for latest earnings call summary
        print("  📥 RAG returned insufficient data, falling back to Tavily...")
        try:
            from tools.search_tools import tavily_broad_search
            web_result = await tavily_broad_search.ainvoke({
                "query": f"{company} latest earnings call guidance key highlights",
                "limit": 3,
            })
            guidance_output = {
                "executive_summary": prune_context(str(web_result), 2000),
                "source": "web_fallback",
            }
        except Exception as exc:
            print(f"  ⚠️ Tavily fallback also failed: {exc}")
            guidance_output = {"executive_summary": "", "source": "no_data"}

    return {
        "mgmt_guidance": {
            "guidance_tracker": guidance_output.get("guidance_tracker", []),
            "tone_shifts": guidance_output.get("tone_shifts", []),
            "analyst_dodges": guidance_output.get("analyst_dodges", []),
            "executive_summary": guidance_output.get("executive_summary", ""),
            "key_phrases_flagged": guidance_output.get("key_phrases_flagged", []),
            "source": guidance_output.get("source", "rag_narrative_decoder" if concall_text else "web_fallback"),
        }
    }
