"""
prowess_ie_fetcher.py
=====================
Thin helper that wraps Prowess API fetch + clean_json into a single callable.

Usage:
    from projections.prowess_ie_fetcher import fetch_clean_ie_statement
    psv_string = fetch_clean_ie_statement("Hindustan Unilever Ltd.")
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure root is importable
_BASE_DIR = Path(__file__).resolve().parent.parent
if str(_BASE_DIR) not in sys.path:
    sys.path.append(str(_BASE_DIR))

from provess_client.make_request import get_company_id, get_report
from provess_client.clean_json import clean_single_report


def fetch_clean_ie_statement(company_name: str) -> str | None:
    """
    Fetch Income & Expenditure Summary from the Prowess CMIE API,
    clean it via clean_json.clean_single_report(), and return a PSV string.

    Returns None if the fetch or cleaning fails (network error, unknown
    company, no data in the report, etc.).

    Parameters
    ----------
    company_name : str
        The full legal name of the company as it appears in the Prowess
        registry (case-insensitive match via cpy_cin_code.dt file).

    Returns
    -------
    str | None
        Pipe-separated-values string of the cleaned Income & Expenditure
        Summary, or None on failure.
    """
    try:
        co_id = get_company_id(company_name)
        print(f"[prowess_ie_fetcher] Resolved {company_name!r} → co_code={co_id}")
    except ValueError as exc:
        print(f"[prowess_ie_fetcher] Company lookup failed: {exc}")
        return None

    try:
        raw_json_str = get_report(co_id, "Income_Expenditure_Summary")
        payload = json.loads(raw_json_str)
    except json.JSONDecodeError as exc:
        print(f"[prowess_ie_fetcher] Prowess returned invalid JSON: {exc}")
        return None
    except Exception as exc:
        print(f"[prowess_ie_fetcher] Prowess API call failed: {exc}")
        return None

    psv = clean_single_report(company_name, "Income_Expenditure_Summary", payload)
    if psv is None:
        print(f"[prowess_ie_fetcher] clean_single_report returned None (no data or error in payload)")
        return None

    print(f"[prowess_ie_fetcher] ✅ Cleaned I&E statement: {len(psv)} chars, "
          f"{psv.count(chr(10))+1} lines")
    return psv


# ── Quick smoke test ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_company = sys.argv[1] if len(sys.argv) > 1 else "Hindustan Unilever Ltd."
    result = fetch_clean_ie_statement(test_company)
    if result:
        print("\n" + "=" * 70)
        print(result[:2000])
        if len(result) > 2000:
            print(f"\n... ({len(result) - 2000} more chars)")
    else:
        print("[FAIL] No data returned.")
