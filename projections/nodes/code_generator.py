"""
code_generator.py — LLM-Generated Python Projection Code
==========================================================
Generates Python code that computes multi-year projections based on
locked assumptions. Each line item gets its own formula based on projection_method.

The generated code is REVIEWED by the analyst before execution.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from langchain_core.messages import HumanMessage, SystemMessage
from projections.llm_providers import get_chat_model


CODE_GEN_SYSTEM_PROMPT = """You are a Python code generator for financial projections.

CRITICAL RULES:
1. Output ONLY executable Python code. No markdown fences. No explanations.
2. Define a function `run_projection(assumptions: dict) -> dict` that returns the projection results.
3. Use ONLY standard Python (math, statistics). NO imports of external libraries.
4. The function receives the full assumptions package as a dict.
5. The function must return a dict with:
   - "projected_years": ["FY25E", "FY26E", "FY27E"]
   - "projections": {
       "Revenue": {"FY25E": 12345.0, "FY26E": 13456.0, ...},
       "Raw Materials": {"FY25E": ..., ...},
       ...
     }
   - "derived_items": {
       "EBITDA": {...}, "EBIT": {...}, "PBT": {...},
       "Tax": {...}, "PAT": {...}, "EPS": {...}
     }
6. Each line item uses the projection_method specified in its assumption:
   - cagr: base * (1 + rate/100) ** year_index
   - pct_of_revenue: projected_revenue * pct/100
   - step_down_growth: base * product(1 + rate_i/100 for rates in trajectory)
   - fixed_amount: same value each year
   - linked_to_item: reference_item * linked_rate/100
   - custom: eval the custom_formula string
7. After computing all items, derive below-the-line:
   - EBITDA = Revenue - sum(expense items except depreciation and interest)
   - EBIT = EBITDA - Depreciation
   - PBT = EBIT - Interest Expense
   - Tax = PBT * tax_rate/100
   - PAT = PBT - Tax
   - EPS = PAT / shares_outstanding (in crores)
8. All values in ₹ Crores. Round to 2 decimal places.
9. Handle edge cases: if a value is None or missing, use 0.0 as default.
10. The code MUST be safe to execute in a sandboxed subprocess."""


async def code_generator_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Use LLM to generate Python projection code based on locked assumptions.
    """
    assumptions = state.get("locked_assumptions", state.get("draft_assumptions", {}))
    company = state.get("company_name", "")

    print(f"\n{'='*60}")
    print(f"🔧 CODE GENERATOR: {company}")
    print(f"{'='*60}")

    prompt = f"""Generate Python projection code for {company}.

LOCKED ASSUMPTIONS:
{json.dumps(assumptions, indent=2, default=str)[:8000]}

The function signature must be:
def run_projection(assumptions: dict) -> dict

Remember: ONLY output Python code. No markdown. No explanations."""

    llm = get_chat_model("deepseek", temperature=0)
    response = await llm.ainvoke([
        SystemMessage(content=CODE_GEN_SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])

    code = response.content.strip()
    # Strip markdown fences if present
    if code.startswith("```"):
        code = code.split("\n", 1)[1] if "\n" in code else code[3:]
        code = code.rsplit("```", 1)[0]

    # Validate it at least has the expected function signature
    if "def run_projection" not in code:
        print("  ⚠️ Generated code missing run_projection function — wrapping")
        code = f"def run_projection(assumptions: dict) -> dict:\n    # Auto-wrapped\n    {code}"

    line_count = code.count("\n") + 1
    print(f"  ✅ Generated {line_count} lines of projection code")

    return {
        "generated_projection_code": code,
        "code_approved": False,
    }
