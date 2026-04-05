"""
materiality.py
==============
Materiality checks for the Financial Projections pipeline.

Identifies material revenue segments (>threshold) and material expense
line items (>revenue_threshold) from the financial data.

Supports TWO data shapes:
  1. Pre-structured dict: {"segments": {...}, "expenses": {...}, "total_revenue": float}
     (e.g. from ie_parser.parse_ie_psv or manual construction)
  2. Raw Prowess I&E PSV string: auto-parsed via ie_parser if the PSV is available in state

The orchestrator_node calls these functions and sets the parallel
router variables (material_segments, material_line_items).
"""

from typing import Dict, List, Any, Optional


def identify_material_segments(financial_data: Dict[str, Any], threshold: float = 0.05) -> List[str]:
    """
    Identifies revenue segments that contribute more than the threshold (default 5%)
    to the total revenue base, isolating them for parallel research analysis.
    
    Args:
        financial_data: The fetched financial JSON structure.
            Expected keys: "segments" (dict of name→value), "total_revenue" (float).
        threshold: The fractional percentage threshold (0.05 = 5%).
    
    Returns:
        List of segment names exceeding the threshold.
    """
    material = []
    
    # Safely extract segments, substituting with an empty dict if not found
    segments = financial_data.get("segments", {})
    total_revenue = financial_data.get("total_revenue", sum(segments.values()) if segments else 0)
    
    if total_revenue <= 0:
        return material
        
    for segment_name, segment_value in segments.items():
        try:
            if (float(segment_value) / total_revenue) >= threshold:
                material.append(segment_name)
        except (ValueError, TypeError):
            continue
            
    return material


def identify_material_expenses(financial_data: Dict[str, Any], revenue_threshold: float = 0.20) -> List[str]:
    """
    Identifies expense line items that make up a significant portion of the total revenue
    (default 20%). This guides the model to only research the largest cost drivers.

    Args:
        financial_data: The fetched financial JSON structure.
            Expected keys: "expenses" (dict of name→value), "total_revenue" (float).
            Also accepts "expense_line_items" as an alias for "expenses".
        revenue_threshold: The fractional percentage threshold (0.20 = 20%).
    
    Returns:
        List of expense names exceeding the threshold.
    """
    material = []
    
    # Accept either "expenses" or "expense_line_items" (ie_parser produces both)
    expenses = financial_data.get("expenses", financial_data.get("expense_line_items", {}))
    total_revenue = financial_data.get("total_revenue", 1.0)  # Avoid div-by-zero
    
    if total_revenue <= 0:
        total_revenue = 1.0
    
    for expense_name, expense_value in expenses.items():
        try:
            if (float(expense_value) / total_revenue) >= revenue_threshold:
                material.append(expense_name)
        except (ValueError, TypeError):
            continue
            
    return material


def enrich_financial_data_from_psv(
    financial_data: Dict[str, Any],
    ie_psv: Optional[str],
) -> Dict[str, Any]:
    """
    Enrich the financial_data dict with parsed I&E data from a Prowess PSV string.

    If the financial_data already has populated "expenses" and "total_revenue",
    this is a no-op (existing data takes precedence). Otherwise, the PSV is parsed
    and merged in.

    Parameters
    ----------
    financial_data : dict
        The existing financial_data from ProjectionState.
    ie_psv : str or None
        The cleaned I&E PSV string from prowess_ie_fetcher / state.

    Returns
    -------
    dict
        Enriched financial_data with "expenses", "total_revenue", etc. from the PSV.
    """
    if not ie_psv:
        return financial_data

    # Don't overwrite if financial_data already has real expense data
    existing_expenses = financial_data.get("expenses", {})
    if existing_expenses and financial_data.get("total_revenue", 0) > 0:
        return financial_data

    # Lazy import to avoid circular dependency at module level
    from provess_client.ie_parser import parse_ie_psv

    parsed = parse_ie_psv(ie_psv)

    # Merge parsed data into financial_data (parsed values fill gaps)
    enriched = {**financial_data}

    if not enriched.get("total_revenue") or enriched["total_revenue"] <= 0:
        enriched["total_revenue"] = parsed.get("total_revenue", 0.0)

    if not enriched.get("expenses"):
        enriched["expenses"] = parsed.get("expenses", {})

    if not enriched.get("expense_line_items"):
        enriched["expense_line_items"] = parsed.get("expense_line_items", {})

    if not enriched.get("all_line_items"):
        enriched["all_line_items"] = parsed.get("all_line_items", {})

    enriched.setdefault("ie_fiscal_year", parsed.get("fiscal_year", "unknown"))
    enriched.setdefault("ie_source", parsed.get("source", "prowess_ie_statement"))

    return enriched


# ── PROMPTS ──────────────────────────────────────────────────────────────────

ORCHESTRATOR_PROMPT = """
You are the orchestrator for the Financial Projections Agent.
Based on the company data and business model, your job is to review the quantitative material
segments and expenses provided and set up the plan for deep research.
"""

SYNTHESIZER_PROMPT = """
You are the Synthesizer. You take the raw notes and numerical insights from the parallel segment
and expense researchers and format them into structured JSON mathematical inputs for the formula tools.
"""
