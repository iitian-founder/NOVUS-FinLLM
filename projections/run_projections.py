"""
run_projections.py
==================
Entry point that bridges the CIO Research Pipeline → Financial Projections Graph.

This script:
  1. Runs the CIO pipeline (or loads a cached result) to get the executive summary.
  2. Fetches + cleans the Income & Expenditure Statement from Prowess CMIE.
  3. Invokes the LangGraph financial projections graph with pre-computed context.

Usage:
    # Full pipeline: CIO → Projections
    python -m projections.run_projections --company "Hindustan Unilever Ltd." --ticker HINDUNILVR

    # Standalone (no CIO, falls back to Tavily + RAG):
    python -m projections.run_projections --company "Hindustan Unilever Ltd." --ticker HINDUNILVR --standalone

    # With a pre-saved CIO report JSON:
    python -m projections.run_projections --company "Hindustan Unilever Ltd." --ticker HINDUNILVR --cio-report path/to/report.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Ensure root is importable
_BASE_DIR = Path(__file__).resolve().parent.parent
if str(_BASE_DIR) not in sys.path:
    sys.path.append(str(_BASE_DIR))


def _extract_executive_summary_from_cio(cio_state) -> str:
    """
    Extract the executive_summary string from a completed CIO OrchestratorState.

    Tries multiple paths since the CIO output structure can vary:
      1. cio_state.final_thesis.findings["executive_summary"]
      2. cio_state.final_report (full text fallback)
    """
    # Path 1: Structured findings
    if hasattr(cio_state, "final_thesis") and cio_state.final_thesis:
        findings = getattr(cio_state.final_thesis, "findings", None)
        if isinstance(findings, dict):
            exec_summary = findings.get("executive_summary")
            if exec_summary and isinstance(exec_summary, str):
                print(f"[run_projections] ✅ Extracted executive_summary from CIO findings ({len(exec_summary)} chars)")
                return exec_summary

    # Path 2: Full report text fallback
    if hasattr(cio_state, "final_report") and cio_state.final_report:
        report = cio_state.final_report
        if isinstance(report, str) and len(report) > 50:
            print(f"[run_projections] ⚠️  Using full final_report as exec summary fallback ({len(report)} chars)")
            return report[:5000]  # Cap to avoid excessive context

    return ""


def _load_cio_report_from_json(path: Path) -> str:
    """Load a pre-saved CIO report JSON and extract executive_summary."""
    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    # Try standard fields
    if isinstance(data, dict):
        if "executive_summary" in data:
            return data["executive_summary"]
        if "final_report" in data:
            return data["final_report"][:5000]
        # If it's a full agent_trails structure
        pm = data.get("agent_trails", {}).get("pm_synthesis", {})
        if isinstance(pm, dict):
            findings = pm.get("findings", {})
            if isinstance(findings, dict) and "executive_summary" in findings:
                return findings["executive_summary"]

    return json.dumps(data, indent=2)[:5000]


async def run_projections(
    company_name: str,
    ticker: str,
    executive_summary: str = "",
    ie_psv: str | None = None,
    financial_data: dict | None = None,
) -> dict:
    """
    Run the financial projections graph with optional pre-computed context.

    Parameters
    ----------
    company_name : str
        Full legal company name.
    ticker : str
        Stock ticker symbol.
    executive_summary : str
        Pre-computed executive summary from CIO pipeline. Empty = standalone mode.
    ie_psv : str or None
        Cleaned I&E PSV string from Prowess. None = skip.
    financial_data : dict or None
        Existing financial data dict. None = empty dict.

    Returns
    -------
    dict
        The final ProjectionState after graph execution.
    """
    from projections.graph import build_projections_graph

    graph = build_projections_graph()

    initial_state = {
        "company_name": company_name,
        "financial_data": financial_data or {"ticker": ticker},
        "messages": [],
    }

    # Inject upstream context if available
    if executive_summary:
        initial_state["executive_summary"] = executive_summary
        print(f"[run_projections] 📥 Executive summary injected ({len(executive_summary)} chars)")

    if ie_psv:
        initial_state["income_expenditure_psv"] = ie_psv
        print(f"[run_projections] 📥 I&E PSV injected ({len(ie_psv)} chars)")

    if not executive_summary and not ie_psv:
        print("[run_projections] 📡 Standalone mode — no upstream context. Using Tavily + RAG.")

    print(f"\n{'='*70}")
    print(f"  LAUNCHING FINANCIAL PROJECTIONS GRAPH — {company_name} ({ticker})")
    print(f"{'='*70}\n")

    result = await graph.ainvoke(initial_state)
    return result


async def main():
    parser = argparse.ArgumentParser(description="Run Financial Projections Pipeline")
    parser.add_argument("--company", required=True, help="Full legal company name")
    parser.add_argument("--ticker", required=True, help="Stock ticker symbol")
    parser.add_argument("--standalone", action="store_true", help="Skip CIO context, use Tavily + RAG")
    parser.add_argument("--cio-report", type=str, default=None, help="Path to pre-saved CIO report JSON")
    parser.add_argument("--skip-ie", action="store_true", help="Skip Prowess I&E fetch")
    args = parser.parse_args()

    executive_summary = ""
    ie_psv = None

    # ── Step 1: Get executive summary ────────────────────────────────────
    if not args.standalone:
        if args.cio_report:
            report_path = Path(args.cio_report)
            if report_path.exists():
                executive_summary = _load_cio_report_from_json(report_path)
                print(f"[run_projections] Loaded CIO report from {report_path}")
            else:
                print(f"[run_projections] ⚠️  CIO report not found: {report_path}")
        else:
            print("[run_projections] No --cio-report provided. To use CIO context, pass --cio-report <path>.")
            print("                  Proceeding without executive summary.")

    # ── Step 2: Fetch + clean I&E from Prowess ───────────────────────────
    if not args.skip_ie:
        try:
            from provess_client.prowess_ie_fetcher import fetch_clean_ie_statement
            ie_psv = fetch_clean_ie_statement(args.company)
        except Exception as e:
            print(f"[run_projections] ⚠️  Prowess I&E fetch failed: {e}")
            ie_psv = None

    # ── Step 3: Run projections graph ────────────────────────────────────
    result = await run_projections(
        company_name=args.company,
        ticker=args.ticker,
        executive_summary=executive_summary,
        ie_psv=ie_psv,
    )

    # ── Step 4: Print results ────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("  PROJECTION RESULTS")
    print(f"{'='*70}")

    bmc = result.get("business_model_context", {})
    if bmc:
        print(f"\n📊 Company: {bmc.get('company_identity', {}).get('full_name', 'N/A')}")
        print(f"   Industry: {bmc.get('industry_classification', 'N/A')}")
        print(f"   Segments: {len(bmc.get('revenue_segments', []))}")
        print(f"   Data Sources: {bmc.get('data_sources', [])}")

    print(f"\n   Material Segments: {result.get('material_segments', [])}")
    print(f"   Material Expenses: {result.get('material_line_items', [])}")

    final = result.get("final_projection", {})
    if final:
        print(f"\n   Final Projection: {json.dumps(final, indent=2, default=str)}")

    return result


if __name__ == "__main__":
    asyncio.run(main())
