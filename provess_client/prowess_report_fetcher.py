"""
prowess_report_fetcher.py
==========================
Generic CMIE Prowess report fetcher. Extends the existing I&E-specific fetcher
to support any batch file report type: Balance Sheet, Capex, Capital History, Cash Flow, etc.

Usage:
    from provess_client.prowess_report_fetcher import fetch_clean_report, fetch_all_projection_reports
    
    balance_sheet = fetch_clean_report(co_id, "Balance_Sheet_Summary")
    all_reports = fetch_all_projection_reports("Hindustan Unilever Ltd.")
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Ensure root is importable
_BASE_DIR = Path(__file__).resolve().parent.parent
if str(_BASE_DIR) not in sys.path:
    sys.path.append(str(_BASE_DIR))

from provess_client.make_request import get_company_id, get_report
from provess_client.clean_json import clean_single_report


# Reports needed for the full P&L waterfall projection
PROJECTION_REPORTS = [
    "Balance_Sheet_Summary",
    "Capital_Expenditure_Projects",
    "Capital_History_Summary",
    "Cash_Flow",
]


def fetch_clean_report(
    company_id: int,
    report_name: str,
    company_name: str = "",
) -> Optional[str]:
    """
    Fetch any Prowess report by name, clean it, and return the PSV string.

    Parameters
    ----------
    company_id : int
        The Prowess co_code (from get_company_id).
    report_name : str
        The batch file name (without .json extension), e.g. "Balance_Sheet_Summary".
    company_name : str, optional
        Company name for logging and clean_single_report. Defaults to empty.

    Returns
    -------
    str | None
        Pipe-separated-values string of the cleaned report, or None on failure.
    """
    batch_file = Path(__file__).resolve().parent / "batch_files" / f"{report_name}.json"
    if not batch_file.exists():
        print(f"[prowess_report_fetcher] ⚠️  Batch file not found: {batch_file}")
        return None

    try:
        raw_json_str = get_report(company_id, report_name)
        payload = json.loads(raw_json_str)
    except json.JSONDecodeError as exc:
        print(f"[prowess_report_fetcher] Prowess returned invalid JSON for {report_name}: {exc}")
        return None
    except Exception as exc:
        print(f"[prowess_report_fetcher] Prowess API call failed for {report_name}: {exc}")
        return None

    psv = clean_single_report(company_name or "unknown", report_name, payload)
    if psv is None:
        print(f"[prowess_report_fetcher] clean_single_report returned None for {report_name}")
        return None

    print(
        f"[prowess_report_fetcher] ✅ {report_name}: {len(psv)} chars, "
        f"{psv.count(chr(10)) + 1} lines"
    )
    return psv


def fetch_all_projection_reports(
    company_name: str,
) -> Dict[str, Optional[str]]:
    """
    Fetch all CMIE reports needed for the full P&L waterfall projection.

    Returns a dict with keys:
        "Balance_Sheet_Summary", "Capital_Expenditure_Projects",
        "Capital_History_Summary", "Cash_Flow"
    
    Each value is the cleaned PSV string or None if the fetch failed.
    """
    try:
        co_id = get_company_id(company_name)
        print(f"[prowess_report_fetcher] Resolved {company_name!r} → co_code={co_id}")
    except ValueError as exc:
        print(f"[prowess_report_fetcher] Company lookup failed: {exc}")
        return {name: None for name in PROJECTION_REPORTS}

    results: Dict[str, Optional[str]] = {}
    for report_name in PROJECTION_REPORTS:
        results[report_name] = fetch_clean_report(co_id, report_name, company_name)

    fetched = sum(1 for v in results.values() if v is not None)
    print(f"[prowess_report_fetcher] 📊 Fetched {fetched}/{len(PROJECTION_REPORTS)} reports")
    return results


# ── Quick smoke test ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_company = sys.argv[1] if len(sys.argv) > 1 else "Hindustan Unilever Ltd."
    reports = fetch_all_projection_reports(test_company)
    for name, psv in reports.items():
        if psv:
            print(f"\n{'=' * 70}")
            print(f"📄 {name}")
            print("=" * 70)
            print(psv[:1000])
            if len(psv) > 1000:
                print(f"\n... ({len(psv) - 1000} more chars)")
        else:
            print(f"\n❌ {name}: No data returned")
