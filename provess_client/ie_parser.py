"""
ie_parser.py
============
Parses a cleaned Income & Expenditure PSV string (from clean_json / prowess_ie_fetcher)
into a structured dict that materiality.py can consume.

The Prowess I&E Summary has line items like:
    Sales Turnover | 60,000 | 62,500 | ...
    Raw Materials Consumed | 28,000 | 29,000 | ...
    Power & Fuel Cost | 1,200 | 1,300 | ...
    Total Expenses | 50,000 | 52,000 | ...

This parser extracts the LATEST fiscal year column and produces:
    {
        "total_revenue": 62500.0,
        "segments": {},          # Prowess I&E doesn't have segment splits
        "expenses": {
            "Raw Materials Consumed": 29000.0,
            "Power & Fuel Cost": 1300.0,
            ...
        },
        "expense_line_items": {...},  # same as expenses (alias for downstream)
        "fiscal_year": "Mar 2024",
        "source": "prowess_ie_statement"
    }

Note: Prowess I&E does NOT include segment-level revenue decomposition.
      Segment data comes from a separate Prowess report or from the
      company_overview_node's LLM extraction.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional


# ── Revenue line label patterns (case-insensitive) ───────────────────────────
_REVENUE_PATTERNS = [
    re.compile(r"^sales\s*turnover$", re.IGNORECASE),
    re.compile(r"^net\s*sales$", re.IGNORECASE),
    re.compile(r"^total\s*income\s*from\s*operations$", re.IGNORECASE),
    re.compile(r"^revenue\s*from\s*operations$", re.IGNORECASE),
    re.compile(r"^total\s*revenue$", re.IGNORECASE),
    re.compile(r"^income\s*from\s*operations$", re.IGNORECASE),
]

# ── Expense line label patterns to SKIP (totals, subtotals, non-expenses) ────
_SKIP_PATTERNS = [
    re.compile(r"^total\s*(expenses?|expenditure)$", re.IGNORECASE),
    re.compile(r"^sales\s*turnover$", re.IGNORECASE),
    re.compile(r"^net\s*sales$", re.IGNORECASE),
    re.compile(r"^other\s*income$", re.IGNORECASE),
    re.compile(r"^total\s*income", re.IGNORECASE),
    re.compile(r"^revenue\s*from\s*operations$", re.IGNORECASE),
    re.compile(r"^profit", re.IGNORECASE),
    re.compile(r"^loss", re.IGNORECASE),
    re.compile(r"^earning", re.IGNORECASE),
    re.compile(r"^tax\s*on", re.IGNORECASE),
    re.compile(r"^provision\s*for\s*tax", re.IGNORECASE),
    re.compile(r"^net\s*profit", re.IGNORECASE),
    re.compile(r"^ebitda$", re.IGNORECASE),
    re.compile(r"^reported\s*net\s*profit", re.IGNORECASE),
    re.compile(r"^dividend", re.IGNORECASE),
    re.compile(r"^equity\s*dividend", re.IGNORECASE),
    re.compile(r"^eps", re.IGNORECASE),
    re.compile(r"^book\s*value", re.IGNORECASE),
    re.compile(r"^extraordinary\s*items", re.IGNORECASE),
]


def _parse_number(s: str) -> Optional[float]:
    """Best-effort float parse of a PSV cell value."""
    s = s.strip()
    if not s or s == "-":
        return None
    # Remove commas and whitespace
    cleaned = s.replace(",", "").replace(" ", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _is_revenue_line(label: str) -> bool:
    return any(p.match(label.strip()) for p in _REVENUE_PATTERNS)


def _should_skip(label: str) -> bool:
    return any(p.match(label.strip()) for p in _SKIP_PATTERNS)


def _get_empty_result() -> Dict[str, Any]:
    return {
        "total_revenue": 0.0,
        "segments": {},
        "expenses": {},
        "expense_line_items": {},
        "fiscal_year": "unknown",
        "source": "prowess_ie_statement",
        "all_line_items": {},
    }


def _extract_data_lines(psv_text: str) -> list[str]:
    data_lines = []
    for line in psv_text.strip().split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            data_lines.append(stripped)
    return data_lines


def _find_header_info(data_lines: list[str]) -> tuple[int, list[str]]:
    fiscal_year_re = re.compile(r"(Mar|Jun|Sep|Dec)\s*\d{4}")
    header_end_idx = 0
    col_labels = []
    for i, line in enumerate(data_lines):
        cells = line.split("|")
        year_matches = [c.strip() for c in cells if fiscal_year_re.match(c.strip())]
        if year_matches:
            col_labels = [c.strip() for c in cells]
            header_end_idx = i + 1

    if not col_labels and data_lines:
        col_labels = [c.strip() for c in data_lines[0].split("|")]
        header_end_idx = 1
    return header_end_idx, col_labels


def _get_latest_fy_col(col_labels: list[str]) -> tuple[int, str]:
    fiscal_year_re = re.compile(r"(Mar|Jun|Sep|Dec)\s*\d{4}")
    latest_fy_col = -1
    latest_fy_label = "unknown"
    for idx, label in enumerate(col_labels):
        if fiscal_year_re.match(label):
            latest_fy_col = idx
            latest_fy_label = label

    if latest_fy_col < 0:
        latest_fy_col = len(col_labels) - 1 if col_labels else -1
    return latest_fy_col, latest_fy_label


def parse_ie_psv(psv_text: str) -> Dict[str, Any]:
    """
    Parse a cleaned Prowess I&E PSV string into a structured dict.

    Parameters
    ----------
    psv_text : str
        The pipe-separated-values text from clean_json / prowess_ie_fetcher.

    Returns
    -------
    dict
        Structured financial data compatible with materiality.py:
        {
            "total_revenue": float,
            "segments": {},
            "expenses": {"label": float, ...},
            "expense_line_items": {"label": float, ...},
            "fiscal_year": str,
            "source": "prowess_ie_statement",
            "all_line_items": {"label": float, ...}
        }
    """
    if not psv_text or not psv_text.strip():
        return _get_empty_result()

    data_lines = _extract_data_lines(psv_text)
    if not data_lines:
        return _get_empty_result()

    header_end_idx, col_labels = _find_header_info(data_lines)
    latest_fy_col, latest_fy_label = _get_latest_fy_col(col_labels)

    all_line_items: Dict[str, float] = {}
    total_revenue = 0.0
    expenses: Dict[str, float] = {}

    for line in data_lines[header_end_idx:]:
        cells = line.split("|")
        if len(cells) < 2:
            continue

        label = cells[0].strip()
        if not label:
            continue

        value = None
        if 0 < latest_fy_col < len(cells):
            value = _parse_number(cells[latest_fy_col])

        if value is None:
            continue

        all_line_items[label] = value

        if _is_revenue_line(label):
            total_revenue = max(total_revenue, abs(value))
        elif not _should_skip(label) and value > 0:
            expenses[label] = abs(value)

    return {
        "total_revenue": total_revenue,
        "segments": {},  # I&E doesn't have segment data; filled by company_overview LLM
        "expenses": expenses,
        "expense_line_items": expenses,  # alias
        "fiscal_year": latest_fy_label,
        "source": "prowess_ie_statement",
        "all_line_items": all_line_items,
    }


# ── Quick smoke test ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json as _json
    import sys

    if len(sys.argv) > 1:
        from pathlib import Path
        psv_path = Path(sys.argv[1])
        psv_text = psv_path.read_text(encoding="utf-8")
    else:
        # Demo PSV for testing
        psv_text = """\
# META
# company: HINDUSTAN UNILEVER LTD.
# report: Income_Expenditure_Summary

|Mar 2020|Mar 2021|Mar 2022|Mar 2023|Mar 2024
Sales Turnover|38,785|46,575|51,468|58,154|60,580
Raw Materials Consumed|15,800|19,500|22,000|25,000|26,200
Power & Fuel Cost|1,100|1,250|1,400|1,500|1,600
Employee Cost|2,800|3,100|3,400|3,700|4,000
Other Manufacturing Expenses|3,500|4,000|4,500|5,000|5,300
Selling and Admin Expenses|6,800|7,500|8,200|9,000|9,500
Depreciation|1,200|1,350|1,500|1,650|1,800
Total Expenses|31,200|36,700|41,000|45,850|48,400
Reported Net Profit|6,738|8,076|8,818|10,282|10,276
EPS|15.75|18.87|20.6|24.02|24.01
"""

    result = parse_ie_psv(psv_text)
    print(_json.dumps(result, indent=2, default=str))
