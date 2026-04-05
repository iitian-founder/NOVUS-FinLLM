"""
guidance_deviation_check.py — Assumption vs Management Guidance Verification
==============================================================================
Compares each draft assumption against management guidance and flags deviations.
Does NOT change any assumptions — only adds deviation flags for the analyst.

Severity levels:
  🟢 green — aligned with guidance, or guidance credibility is LOW
  🟡 amber — moderate deviation + moderate credibility
  🔴 red   — large deviation from HIGH-credibility guidance
"""

from __future__ import annotations

from typing import Any, Dict


def guidance_deviation_check_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compare draft assumptions against management guidance and produce deviation flags.
    """
    assumptions = state.get("draft_assumptions", {})
    guidance = state.get("mgmt_guidance", {})

    print(f"\n{'='*60}")
    print(f"⚖️ GUIDANCE DEVIATION CHECK")
    print(f"{'='*60}")

    guidance_tracker = guidance.get("guidance_tracker", [])
    tone_shifts = guidance.get("tone_shifts", [])

    deviation_flags = []

    # Build a lookup from guidance topics to guided data
    guided_topics: Dict[str, Dict] = {}
    for g in guidance_tracker:
        topic = g.get("topic", "").lower() if isinstance(g, dict) else ""
        if topic:
            guided_topics[topic] = g

    # Check each revenue assumption against guidance
    for a in assumptions.get("revenue_assumptions", []):
        if not isinstance(a, dict):
            continue
        item_lower = a.get("line_item", "").lower()
        growth = a.get("projected_growth_rate_pct", 0) or 0

        # Find matching guidance (fuzzy match by keyword overlap)
        matched = None
        for topic, g_data in guided_topics.items():
            item_words = set(item_lower.split())
            topic_words = set(topic.split())
            if item_words & topic_words:  # any overlapping words
                matched = g_data
                break

        if matched:
            credibility = (matched.get("credibility", "MEDIUM") or "MEDIUM").upper()
            prior_guidance = matched.get("prior_guidance", "")

            flag = {
                "line_item": a.get("line_item", ""),
                "your_assumption": f"{growth}% growth",
                "mgmt_said": prior_guidance,
                "mgmt_credibility": credibility,
                "deviation_severity": "green",
                "note": "",
            }

            if credibility == "LOW":
                flag["note"] = "⚠️ Management credibility is LOW on this topic — your bottom-up is likely more reliable"
                flag["deviation_severity"] = "green"
            elif credibility == "HIGH":
                flag["note"] = "🔴 Management credibility is HIGH — large deviation warrants investigation"
                flag["deviation_severity"] = "red"
            else:
                flag["deviation_severity"] = "amber"
                flag["note"] = "🟡 Moderate deviation from management guidance — review recommended"

            deviation_flags.append(flag)
            severity_icon = {"green": "🟢", "amber": "🟡", "red": "🔴"}[flag["deviation_severity"]]
            print(f"  {severity_icon} {flag['line_item']}: {flag['your_assumption']} vs mgmt: {prior_guidance[:60]}")

    # Check for significant tone shifts
    tone_warnings = []
    for shift in tone_shifts:
        if not isinstance(shift, dict):
            continue
        significance = (shift.get("significance", "") or "").upper()
        if significance == "HIGH":
            tone_warnings.append({
                "topic": shift.get("topic", ""),
                "shift": f"{shift.get('prior_tone', '?')} → {shift.get('current_tone', '?')}",
                "warning": f"⚠️ Management tone shifted significantly on {shift.get('topic', '?')} — may affect assumptions",
            })
            print(f"  ⚠️ Tone shift: {shift.get('topic', '?')}")

    if not deviation_flags:
        print("  ℹ️ No matching guidance topics found — proceeding without deviation flags")

    return {
        "deviation_flags": {
            "assumption_vs_guidance": deviation_flags,
            "tone_warnings": tone_warnings,
            "guidance_source": guidance.get("source", "unknown"),
            "guidance_summary": guidance.get("executive_summary", ""),
        }
    }
