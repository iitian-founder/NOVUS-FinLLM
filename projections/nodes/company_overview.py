"""
Company Overview Node  (v3)
===========================
First node in the Financial Projections graph.

Improvements over v2:
  1. Accepts pre-computed upstream context (executive_summary + I&E PSV)
     from the CIO pipeline — skips Tavily/RAG when available.
  2. Falls back to Tavily + RAG parallel search for standalone execution.
  3. Tracks data_sources provenance in the structured output.
  4. Async execution — Tavily + RAG run in parallel via asyncio.gather
  5. Structured output — Pydantic schema enforced via .with_structured_output()
  6. Guardrail validation — programmatic check on output completeness
  7. Context pruning — truncate & deduplicate retrieved context
  8. State reducer safety — business_model_context now stores Dict, messages uses add_messages

Default model: DeepSeek (swap via DEFAULT_PROVIDER or pass `provider=` at call site).
"""

import sys
from pathlib import Path
from typing import Any, Dict

from langchain_core.messages import HumanMessage, SystemMessage

# Ensure root is importable
_BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(_BASE_DIR) not in sys.path:
    sys.path.append(str(_BASE_DIR))

from projections.state import ProjectionState
from projections.llm_providers import get_chat_model
from projections.schemas.company_overview import CompanyOverviewSchema, validate_overview
from projections.prompts.company_overview import OVERVIEW_SYSTEM_PROMPT, OVERVIEW_WITH_FINANCIALS_PROMPT
from projections.utils.context_gatherer import gather_context_async, prune_context, MAX_CONTEXT_CHARS_PER_SOURCE, MAX_TOTAL_CONTEXT_CHARS

# ── Configurable defaults ────────────────────────────────────────────────────
DEFAULT_PROVIDER = "deepseek"       # change to "openai", "gemini", etc.
DEFAULT_MODEL    = None             # None → uses the provider's default
DEFAULT_TEMP     = 0.2

# ══════════════════════════════════════════════════════════════════════════════
# 1. CONTEXT BUILDING — 3-branch logic
# ══════════════════════════════════════════════════════════════════════════════

async def _build_context(
    state: ProjectionState,
    company_name: str,
    ticker: str | None,
) -> tuple[str, list[str], str]:
    """
    Build the combined context string using the best available sources.

    Returns (combined_context, data_sources, system_prompt).

    Three paths:
      1. FAST PATH  — both executive_summary + I&E PSV present → skip all searches
      2. PARTIAL PATH — one of them present → supplement with Tavily/RAG
      3. STANDALONE PATH — neither present → original Tavily + RAG parallel search
    """
    exec_summary = state.get("executive_summary")
    ie_psv = state.get("income_expenditure_psv")

    data_sources: list[str] = []

    # ── FAST PATH: Full upstream context available ────────────────────────
    if exec_summary and ie_psv:
        print("\n📥 FAST PATH: Using upstream CIO context. Skipping Tavily + RAG.")
        combined_context = (
            "=== EXECUTIVE SUMMARY (from CIO Research Pipeline) ===\n"
            f"{prune_context(exec_summary, MAX_CONTEXT_CHARS_PER_SOURCE)}\n\n"
            "=== INCOME & EXPENDITURE STATEMENT (Prowess CMIE, Cleaned) ===\n"
            f"{prune_context(ie_psv, MAX_CONTEXT_CHARS_PER_SOURCE)}"
        )
        data_sources = ["cio_executive_summary", "prowess_ie_statement"]
        system_prompt = OVERVIEW_WITH_FINANCIALS_PROMPT
        return combined_context, data_sources, system_prompt

    # ── PARTIAL PATH: Some upstream context + search supplements ─────────
    if exec_summary or ie_psv:
        print("\n📥 PARTIAL PATH: Supplementing upstream context with Tavily/RAG.")
        parts: list[str] = []

        if exec_summary:
            parts.append(
                "=== EXECUTIVE SUMMARY (from CIO Research Pipeline) ===\n"
                + prune_context(exec_summary, MAX_CONTEXT_CHARS_PER_SOURCE)
            )
            data_sources.append("cio_executive_summary")

        if ie_psv:
            parts.append(
                "=== INCOME & EXPENDITURE STATEMENT (Prowess CMIE, Cleaned) ===\n"
                + prune_context(ie_psv, MAX_CONTEXT_CHARS_PER_SOURCE)
            )
            data_sources.append("prowess_ie_statement")

        # Fill gaps with Tavily/RAG
        tavily_ctx, rag_ctx = await gather_context_async(company_name, ticker)
        parts.append(f"=== WEB SEARCH CONTEXT (Tavily) ===\n{tavily_ctx}")
        parts.append(f"=== INTERNAL RAG CONTEXT ===\n{rag_ctx}")
        data_sources.extend(["tavily_search", "rag_retrieval"])

        combined_context = "\n\n".join(parts)
        system_prompt = OVERVIEW_WITH_FINANCIALS_PROMPT if ie_psv else OVERVIEW_SYSTEM_PROMPT
        return combined_context, data_sources, system_prompt

    # ── STANDALONE PATH: Original behavior (no upstream data) ────────────
    print("\n📡 STANDALONE PATH: Gathering context (Tavily + RAG in parallel)...")
    tavily_ctx, rag_ctx = await gather_context_async(company_name, ticker)

    combined_context = (
        "=== WEB SEARCH CONTEXT (Tavily) ===\n" + tavily_ctx +
        "\n\n=== INTERNAL RAG CONTEXT ===\n" + rag_ctx
    )
    data_sources = ["tavily_search", "rag_retrieval"]
    system_prompt = OVERVIEW_SYSTEM_PROMPT
    return combined_context, data_sources, system_prompt

# ══════════════════════════════════════════════════════════════════════════════
# 2. MAIN NODE  (async)
# ══════════════════════════════════════════════════════════════════════════════

async def company_overview_node(
    state: ProjectionState,
    *,
    provider: str = DEFAULT_PROVIDER,
    model: str | None = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMP,
) -> Dict[str, Any]:
    """
    LangGraph async node — first step of the financial projections pipeline.

    1. Checks for pre-computed upstream context (exec summary + I&E PSV).
       - If available: uses them directly (FAST PATH — no search latency).
       - If partial:   supplements with Tavily/RAG.
       - If missing:   full Tavily + RAG parallel search (STANDALONE PATH).
    2. Prunes and cleans the context to prevent overflow.
    3. Feeds context into LLM with Pydantic structured-output enforcement.
    4. Validates the output via guardrails.
    5. Returns the structured business overview dict into state.
    """
    company_name = state.get("company_name", "Unknown Company")
    ticker = state.get("financial_data", {}).get("ticker")

    print(f"\n{'='*60}")
    print(f"🔍 COMPANY OVERVIEW NODE — {company_name}")
    print(f"{'='*60}")

    # ── Step 1: Build context (3-branch logic) ───────────────────────────
    print("\n📡 Step 1: Building context...")
    combined_context, data_sources, system_prompt = await _build_context(
        state, company_name, ticker
    )

    # Apply total context cap
    if len(combined_context) > MAX_TOTAL_CONTEXT_CHARS:
        combined_context = combined_context[:MAX_TOTAL_CONTEXT_CHARS] + "\n[... total context truncated ...]"

    print(f"\n✂️  Context built: {len(combined_context)} chars")
    print(f"   Data sources: {data_sources}")

    # Show preview
    print("\n┌── Context Preview ──")
    print(combined_context[:1000] + ("\n..." if len(combined_context) > 1000 else ""))
    print(f"└{'─'*50}")

    # ── Step 2: Invoke LLM with structured output ────────────────────────
    print(f"\n🤖 Step 2: Invoking {provider} (model={model or 'default'}) with structured output...")

    user_message = (
        f"Company: {company_name}\n\n"
        f"Below is the research context gathered for this company.\n"
        f"Use ONLY this context to produce the structured business overview.\n\n"
        f"{combined_context}"
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]

    llm = get_chat_model(provider, model=model, temperature=temperature)
    structured_llm = llm.with_structured_output(CompanyOverviewSchema)

    overview: CompanyOverviewSchema = await structured_llm.ainvoke(messages)

    # Inject data_sources provenance
    overview.data_sources = data_sources

    print("\n✅ Structured output received!")
    print(f"   Company : {overview.company_identity.full_name}")
    print(f"   HQ      : {overview.company_identity.headquarters}")
    print(f"   Tickers : {overview.company_identity.tickers}")
    print(f"   Segments: {len(overview.revenue_segments)}")
    print(f"   Competitors: {len(overview.top_competitors)}")
    print(f"   Risks   : {len(overview.risk_factors)}")
    print(f"   Sources : {overview.data_sources}")

    # ── Step 3: Guardrail validation ──────────────────────────────────────
    print("\n🛡️  Step 3: Running guardrail validation...")
    is_valid, warnings = validate_overview(overview)

    if is_valid:
        print("   ✅ All guardrail checks passed.")
    else:
        print(f"   ⚠️  Guardrail warnings ({len(warnings)}):")
        for w in warnings:
            print(f"      - {w}")

    # ── Step 4: Return state update ───────────────────────────────────────
    overview_dict = overview.model_dump()

    summary_msg = (
        f"Company Overview for {company_name} generated successfully.\n"
        f"Data sources: {', '.join(data_sources)}.\n"
        f"Guardrails: {'PASSED' if is_valid else 'WARNINGS: ' + '; '.join(warnings)}"
    )

    return {
        "business_model_context": overview_dict,
        "messages": [HumanMessage(content=summary_msg)],
    }
