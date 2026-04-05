"""
Test: company_overview_node with REAL API calls.
Company: Hindustan Unilever Limited (HINDUNILVR.NS)

Runs the node directly (not the full graph) so we can see
each step's output: Tavily → RAG → LLM → Guardrails.
"""

import asyncio
import json
import sys
from pathlib import Path

# ── Setup paths & env ────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

from langchain_core.messages import HumanMessage
from projections.nodes.company_overview import company_overview_node


async def main():
    print("=" * 70)
    print("  TEST: company_overview_node  —  Hindustan Unilever Limited")
    print("=" * 70)

    test_state = {
        "messages": [HumanMessage(content="Begin financial analysis")],
        "company_name": "Hindustan Unilever Limited",
        "financial_data": {"ticker": "HINDUNILVR.NS"},
        "business_model_context": None,
        "material_segments": [],
        "segment_results": {},
        "material_line_items": [],
        "expense_results": {},
        "bottom_up_projection": {},
        "mgmt_guidance_projection": {},
        "final_projection": {},
    }

    # Run the node
    result = await company_overview_node(test_state)

    # ── Pretty-print the final structured output ─────────────────────────
    print("\n" + "=" * 70)
    print("  FINAL STRUCTURED OUTPUT (business_model_context)")
    print("=" * 70)

    overview = result.get("business_model_context", {})
    print(json.dumps(overview, indent=2, default=str))

    print("\n" + "-" * 70)
    print("  MESSAGES RETURNED TO STATE")
    print("-" * 70)
    for msg in result.get("messages", []):
        print(msg.content)

    print("\n✅ Test complete.")


if __name__ == "__main__":
    asyncio.run(main())
