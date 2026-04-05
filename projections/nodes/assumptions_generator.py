"""
assumptions_generator.py — Draft Assumptions Generator Node
=============================================================
Synthesizes research from segment_researcher, expense_analyzer,
historical_trends, and mgmt_guidance into structured Assumption objects.

Uses bottom-up research as the BASE. Management guidance is referenced
in reasoning but NOT followed blindly.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from langchain_core.messages import HumanMessage, SystemMessage
from projections.llm_providers import get_chat_model


ASSUMPTIONS_SYSTEM_PROMPT = """You are a senior equity research analyst generating projection assumptions.

You MUST output valid JSON matching the AssumptionsPackage schema exactly.

RULES:
1. Base assumptions on BOTTOM-UP research (segment analysis, expense trends, historical CAGRs)
2. Reference management guidance in your reasoning, but do NOT blindly follow it
3. For each assumption, choose the most appropriate projection_method:
   - "cagr": For items with stable growth (revenue segments, employee costs)
   - "pct_of_revenue": For items tied to revenue (raw materials, selling expenses)
   - "step_down_growth": For items with naturally declining growth
   - "fixed_amount": For items that are roughly stable in absolute terms
   - "linked_to_item": For items derived from others (tax from PBT, depreciation from gross block)
   - "custom": Only if the analyst provides a specific formula
4. Include source_urls for EVERY assumption
5. historical_cagr_pct should match the computed CAGRs from historical_trends
6. confidence reflects data quality: 0.9+ for CMIE data, 0.7 for RAG, 0.5 for web search, 0.3 for LLM estimation
7. Default projection horizon is 3 years
8. All values must be in ₹ Crores"""


async def assumptions_generator_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Synthesize all Phase A research into structured draft assumptions.
    """
    company = state.get("company_name", "")
    print(f"\n{'='*60}")
    print(f"📝 ASSUMPTIONS GENERATOR: {company}")
    print(f"{'='*60}")

    # Gather all inputs
    segment_results = state.get("segment_results", {})
    expense_results = state.get("expense_results", {})
    historical = state.get("historical_analysis", {})
    mgmt_guidance = state.get("mgmt_guidance", {})
    business_context = state.get("business_model_context", {})
    financial_data = state.get("financial_data", {})

    # Build the context for the LLM
    context = {
        "company_name": company,
        "business_model": business_context,
        "segment_research": segment_results,
        "expense_research": expense_results,
        "historical_analysis": {
            "fiscal_years": historical.get("fiscal_years", []),
            "cagrs": historical.get("cagrs", {}),
            "tax_analysis": historical.get("tax_analysis", {}),
            "depreciation_data": historical.get("depreciation_data", {}),
            "debt_data": historical.get("debt_data", {}),
            "shares_data": historical.get("shares_data", {}),
        },
        "mgmt_guidance_context": {
            "summary": mgmt_guidance.get("executive_summary", ""),
            "guidance_tracker": mgmt_guidance.get("guidance_tracker", []),
            "source": mgmt_guidance.get("source", "unknown"),
        },
        "latest_financials": {
            "total_revenue": financial_data.get("total_revenue", 0),
            "expenses": financial_data.get("expenses", {}),
            "fiscal_year": financial_data.get("fiscal_year", "unknown"),
        },
    }

    prompt = f"""Generate projection assumptions for {company}.

RESEARCH DATA:
{json.dumps(context, indent=2, default=str)}

Output a JSON object with this EXACT structure:
{{
  "company_name": "{company}",
  "base_year": "<latest fiscal year, e.g. FY24>",
  "projection_horizon_years": 3,
  "revenue_assumptions": [
    {{
      "line_item": "<segment name>",
      "category": "revenue",
      "base_year_value_cr": <float>,
      "base_year_label": "<e.g. FY24>",
      "projection_method": "<cagr|pct_of_revenue|step_down_growth|fixed_amount|linked_to_item|custom>",
      "projected_growth_rate_pct": <float or null>,
      "growth_trajectory": <list of floats or null>,
      "pct_of_revenue": <float or null>,
      "fixed_value_cr": <float or null>,
      "linked_item": <string or null>,
      "linked_rate_pct": <float or null>,
      "custom_formula": <string or null>,
      "reasoning": "<2-3 sentences>",
      "supporting_facts": ["<bullet 1>", "<bullet 2>"],
      "source_urls": ["<url1>"],
      "confidence": <0.0-1.0>,
      "historical_cagr_pct": <float or null>,
      "is_analyst_overridden": false
    }}
  ],
  "expense_assumptions": [...],
  "other_assumptions": [...],
  "methodology_notes": ["<note1>", "<note2>"]
}}

Include assumptions for ALL material line items plus below-the-line items:
- Depreciation (projection_method: "linked_to_item" or "cagr")
- Interest expense (projection_method: "linked_to_item" or "cagr")
- Tax rate (projection_method: "linked_to_item" linked to PBT)
- Shares outstanding (projection_method: "fixed_amount" unless dilution expected)

Output ONLY the JSON. No markdown fences. No explanations."""

    llm = get_chat_model("deepseek", temperature=0)

    response = await llm.ainvoke([
        SystemMessage(content=ASSUMPTIONS_SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])

    # Parse the LLM output
    raw = response.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 1)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0]

    try:
        assumptions_dict = json.loads(raw.strip())
        n_rev = len(assumptions_dict.get("revenue_assumptions", []))
        n_exp = len(assumptions_dict.get("expense_assumptions", []))
        n_other = len(assumptions_dict.get("other_assumptions", []))
        print(f"  ✅ Generated {n_rev} revenue + {n_exp} expense + {n_other} other assumptions")
    except json.JSONDecodeError as exc:
        print(f"  ⚠️ Failed to parse LLM output as JSON: {exc}")
        assumptions_dict = {
            "company_name": company,
            "base_year": "unknown",
            "projection_horizon_years": 3,
            "revenue_assumptions": [],
            "expense_assumptions": [],
            "other_assumptions": [],
            "methodology_notes": [f"LLM output parsing failed: {exc}"],
        }

    return {"draft_assumptions": assumptions_dict}
