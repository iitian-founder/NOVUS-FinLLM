"""
prompt_books.py
===============
Prompt template registry with lightweight quality scoring.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


PROMPT_BOOK_PATH = Path(__file__).resolve().parent / "data" / "prompt_books.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_store() -> None:
    PROMPT_BOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not PROMPT_BOOK_PATH.exists():
        PROMPT_BOOK_PATH.write_text(json.dumps({"templates": []}, indent=2), encoding="utf-8")


def _load() -> Dict:
    _ensure_store()
    with PROMPT_BOOK_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _save(payload: Dict) -> None:
    _ensure_store()
    with PROMPT_BOOK_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def _extract_variables(raw_prompt: str) -> List[str]:
    return sorted(set(re.findall(r"\{\{([a-zA-Z0-9_]+)\}\}", raw_prompt)))


def evaluate_prompt_quality(raw_prompt: str) -> Dict:
    text = raw_prompt.lower()
    checks = {
        "has_citation_rule": any(k in text for k in ["cite", "source", "citation"]),
        "has_output_structure": any(k in text for k in ["markdown", "json", "table", "structure"]),
        "has_guardrails": any(k in text for k in ["do not", "must", "only use", "if unknown"]),
        "has_risk_section": "risk" in text,
        "has_financial_focus": any(k in text for k in ["revenue", "ebitda", "cash flow", "margin"]),
    }
    score = round(sum(1 for v in checks.values() if v) / len(checks), 3)
    return {"score": score, "checks": checks}


def create_prompt_template(
    title: str,
    raw_prompt: str,
    role_tags: List[str] | None = None,
    expected_output_schema: Dict | None = None,
) -> Dict:
    payload = _load()
    template_id = f"tpl_{uuid.uuid4().hex[:12]}"
    template = {
        "template_id": template_id,
        "version": 1,
        "title": title,
        "raw_prompt": raw_prompt,
        "variables": _extract_variables(raw_prompt),
        "role_tags": role_tags or [],
        "expected_output_schema": expected_output_schema or {},
        "quality": evaluate_prompt_quality(raw_prompt),
        "status": "draft",
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
    }
    payload["templates"].append(template)
    _save(payload)
    return template


def list_prompt_templates() -> List[Dict]:
    return _load().get("templates", [])


def get_prompt_template(template_id: str) -> Dict | None:
    for t in list_prompt_templates():
        if t["template_id"] == template_id:
            return t
    return None


def render_prompt(template_id: str, variables: Dict[str, str]) -> str:
    template = get_prompt_template(template_id)
    if not template:
        raise ValueError(f"Unknown template_id: {template_id}")
    rendered = template["raw_prompt"]
    for k, v in variables.items():
        rendered = rendered.replace(f"{{{{{k}}}}}", str(v))
    return rendered


def improve_prompt_template(template_id: str) -> Dict:
    payload = _load()
    for i, t in enumerate(payload.get("templates", [])):
        if t["template_id"] != template_id:
            continue
        improved_text = t["raw_prompt"]
        if "source" not in improved_text.lower():
            improved_text += "\n\nCite source document names for every material claim."
        if "risk" not in improved_text.lower():
            improved_text += "\nInclude a dedicated Risk Factors section."
        if "if unknown" not in improved_text.lower():
            improved_text += "\nIf the context is insufficient, explicitly say what is missing."

        new_t = dict(t)
        new_t["version"] = int(t.get("version", 1)) + 1
        new_t["raw_prompt"] = improved_text
        new_t["variables"] = _extract_variables(improved_text)
        new_t["quality"] = evaluate_prompt_quality(improved_text)
        new_t["status"] = "approved" if new_t["quality"]["score"] >= 0.8 else "draft"
        new_t["updated_at"] = _utc_now()
        payload["templates"][i] = new_t
        _save(payload)
        return new_t
    raise ValueError(f"Unknown template_id: {template_id}")
