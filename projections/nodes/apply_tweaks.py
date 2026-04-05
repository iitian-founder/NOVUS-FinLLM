"""
apply_tweaks.py — Deterministic Assumption Tweak Node
======================================================
Applies analyst-provided overrides to the draft assumptions.
Purely deterministic: no LLM, just dict patching.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List


def apply_tweaks_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply analyst overrides to the draft assumptions.

    Expected tweak format:
    {
        "line_item": "Home Care Revenue",
        "field": "projected_growth_rate_pct",
        "new_value": 10.0
    }

    Or full replacement:
    {
        "line_item": "Home Care Revenue",
        "projection_method": "step_down_growth",
        "growth_trajectory": [12.0, 10.0, 8.0]
    }
    """
    tweaks = state.get("assumption_tweaks", [])
    assumptions = copy.deepcopy(state.get("draft_assumptions", {}))

    print(f"\n{'='*60}")
    print(f"✏️ APPLYING TWEAKS: {len(tweaks)} modifications")
    print(f"{'='*60}")

    for tweak in tweaks:
        if not isinstance(tweak, dict):
            continue

        target_item = tweak.get("line_item", "")
        if not target_item:
            continue

        # Search across all assumption categories
        for category_key in ["revenue_assumptions", "expense_assumptions", "other_assumptions"]:
            items = assumptions.get(category_key, [])
            for i, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                if item.get("line_item", "").lower() == target_item.lower():
                    # Apply individual field updates
                    if "field" in tweak and "new_value" in tweak:
                        old_val = item.get(tweak["field"])
                        item[tweak["field"]] = tweak["new_value"]
                        item["is_analyst_overridden"] = True
                        print(f"  ✏️ {target_item}.{tweak['field']}: {old_val} → {tweak['new_value']}")
                    else:
                        # Bulk update: merge all tweak fields into the item
                        for k, v in tweak.items():
                            if k != "line_item":
                                item[k] = v
                        item["is_analyst_overridden"] = True
                        print(f"  ✏️ {target_item}: bulk update ({len(tweak) - 1} fields)")

                    items[i] = item
                    break

    return {
        "draft_assumptions": assumptions,
        "assumption_tweaks": [],  # clear tweaks after applying
    }
