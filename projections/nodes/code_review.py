"""
code_review.py — Analyst Code Review Node (HITL)
==================================================
Presents the LLM-generated Python projection code to the analyst for review.
The analyst can approve, edit, or request regeneration.
"""

from __future__ import annotations

from typing import Any, Dict

from langgraph.types import interrupt


def code_review_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Present generated code to analyst for review via interrupt().
    """
    code = state.get("generated_projection_code", "")

    print(f"\n{'='*60}")
    print(f"👀 CODE REVIEW — Waiting for analyst approval...")
    print(f"{'='*60}")

    review_payload = {
        "type": "code_review",
        "company": state.get("company_name", ""),
        "generated_code": code,
        "code_length_lines": code.count("\n") + 1,
        "instructions": (
            "Review the generated projection code.\n"
            "You can:\n"
            "  'approve' — Execute this code to generate projections\n"
            "  'edit' — Provide edited code to replace the generated version\n"
            "  'regenerate' — Request the LLM to regenerate the code\n"
        ),
    }

    # ── INTERRUPT: Wait for analyst ──
    analyst_response = interrupt(review_payload)

    action = analyst_response.get("action", "approve") if isinstance(analyst_response, dict) else "approve"

    if action in ("approve", "approved"):
        print("  ✅ Analyst APPROVED the code")
        return {"code_approved": True}

    elif action == "edit":
        edited_code = analyst_response.get("code", code)
        print(f"  ✏️ Analyst edited the code ({edited_code.count(chr(10)) + 1} lines)")
        return {
            "generated_projection_code": edited_code,
            "code_approved": True,
        }

    else:  # regenerate
        feedback = analyst_response.get("feedback", "")
        print(f"  🔄 Analyst requested regeneration: {feedback[:80]}")
        return {"code_approved": False}
