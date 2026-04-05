"""
analyst_review.py — Analyst Review Node (HITL)
================================================
Presents assumptions + deviation flags to the analyst via interrupt().
The analyst can: approve, ask follow-up questions, tweak assumptions, or change horizon.
"""

from __future__ import annotations

from typing import Any, Dict

from langgraph.types import interrupt


def analyst_review_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Human-in-the-loop node: presents assumptions for analyst review.
    Uses interrupt() to pause execution and wait for analyst input.
    """
    assumptions = state.get("draft_assumptions") or state.get("locked_assumptions", {})
    deviation_flags = state.get("deviation_flags", {})

    print(f"\n{'='*60}")
    print(f"🧑‍💼 ANALYST REVIEW — Waiting for input...")
    print(f"{'='*60}")

    # Format the review payload
    review_payload = {
        "type": "assumptions_review",
        "company": state.get("company_name", ""),
        "base_year": assumptions.get("base_year", ""),
        "projection_years": assumptions.get("projection_horizon_years", 3),

        "revenue_assumptions": [
            {
                "line_item": a.get("line_item", ""),
                "base_value": a.get("base_year_value_cr"),
                "growth_rate": a.get("projected_growth_rate_pct"),
                "projection_method": a.get("projection_method", ""),
                "historical_cagr": a.get("historical_cagr_pct"),
                "reasoning": a.get("reasoning", ""),
                "sources": a.get("source_urls", []),
                "confidence": a.get("confidence", 0),
            }
            for a in assumptions.get("revenue_assumptions", [])
            if isinstance(a, dict)
        ],
        "expense_assumptions": [
            {
                "line_item": a.get("line_item", ""),
                "base_value": a.get("base_year_value_cr"),
                "growth_rate": a.get("projected_growth_rate_pct"),
                "projection_method": a.get("projection_method", ""),
                "reasoning": a.get("reasoning", ""),
                "confidence": a.get("confidence", 0),
            }
            for a in assumptions.get("expense_assumptions", [])
            if isinstance(a, dict)
        ],
        "other_assumptions": [
            {
                "line_item": a.get("line_item", ""),
                "base_value": a.get("base_year_value_cr"),
                "projection_method": a.get("projection_method", ""),
                "reasoning": a.get("reasoning", ""),
            }
            for a in assumptions.get("other_assumptions", [])
            if isinstance(a, dict)
        ],

        # Management guidance deviation flags
        "mgmt_guidance_deviations": deviation_flags.get("assumption_vs_guidance", []),
        "mgmt_tone_warnings": deviation_flags.get("tone_warnings", []),
        "mgmt_guidance_summary": deviation_flags.get("guidance_summary", ""),

        "instructions": (
            "Review the assumptions above. Deviation flags show where your assumptions\n"
            "differ from management guidance (🟢 green = aligned, 🟡 amber = review, 🔴 red = investigate).\n"
            "You can:\n"
            "1. 'approve' — Accept all assumptions and generate projections\n"
            "2. 'ask' — Ask a follow-up question about any assumption or deviation\n"
            "3. 'tweak' — Override one or more assumptions with your own values\n"
            "4. 'horizon' — Change the projection horizon (3 or 5 years)\n"
        ),
    }

    # ── INTERRUPT: Pause and wait for analyst response ──
    analyst_response = interrupt(review_payload)

    # Process the analyst's response
    action = analyst_response.get("action", "approve") if isinstance(analyst_response, dict) else "approve"

    result: Dict[str, Any] = {"analyst_action": action}

    if action == "approved" or action == "approve":
        result["analyst_action"] = "approved"
        result["locked_assumptions"] = assumptions
        print("  ✅ Analyst APPROVED assumptions")

    elif action == "ask" or action == "ask_followup":
        result["analyst_action"] = "ask_followup"
        result["followup_question"] = analyst_response.get("question", "")
        print(f"  ❓ Analyst asked: {result['followup_question'][:80]}")

    elif action == "tweak" or action == "apply_tweaks":
        result["analyst_action"] = "apply_tweaks"
        result["assumption_tweaks"] = analyst_response.get("tweaks", [])
        print(f"  ✏️ Analyst tweaked {len(result['assumption_tweaks'])} assumptions")

    elif action == "horizon":
        result["analyst_action"] = "horizon_changed"
        new_horizon = analyst_response.get("years", 3)
        # Update in assumptions
        updated = {**assumptions, "projection_horizon_years": new_horizon}
        result["draft_assumptions"] = updated
        print(f"  📐 Horizon changed to {new_horizon} years")

    return result
