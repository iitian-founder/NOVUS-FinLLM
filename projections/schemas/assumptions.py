"""
Projection Assumptions Schemas
===============================
Pydantic models for the assumptions pipeline:
  - Assumption: A single line-item projection assumption
  - AssumptionsPackage: Complete set of assumptions for analyst review
  - ManagementGuidance: Structured output from NarrativeDecoderV3
  - DeviationFlag: Comparison of assumption vs management guidance
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ══════════════════════════════════════════════════════════════════════════════
# 1. ASSUMPTION SCHEMA
# ══════════════════════════════════════════════════════════════════════════════

class Assumption(BaseModel):
    """A single projection assumption for one line item."""

    line_item: str = Field(description="e.g. 'Home Care Revenue', 'Raw Materials Cost'")
    category: Literal["revenue", "expense", "other"] = Field(
        description="Whether this is a revenue, expense, or other (tax, depreciation, etc.) item"
    )
    base_year_value_cr: float = Field(description="Actual value in ₹ Crores for the base year")
    base_year_label: str = Field(description="e.g. 'FY24'")

    # ── Projection method (tells the code generator WHAT formula to use) ──
    projection_method: Literal[
        "cagr",               # compound annual growth: base × (1 + rate)^yr
        "pct_of_revenue",     # expense as % of projected revenue: rev × pct
        "step_down_growth",   # declining growth: [12%, 10%, 8%, 7%, 6%]
        "fixed_amount",       # flat absolute value each year
        "linked_to_item",     # derived from another line item (e.g. tax = PBT × rate)
        "custom",             # analyst provides a custom formula string
    ] = Field(description="The projection formula type for this line item")

    # ── Method-specific parameters ──
    projected_growth_rate_pct: Optional[float] = Field(
        default=None, description="For cagr/step_down: annual growth rate in %"
    )
    growth_trajectory: Optional[List[float]] = Field(
        default=None, description="For step_down: per-year growth rates [12.0, 10.0, 8.0, ...]"
    )
    pct_of_revenue: Optional[float] = Field(
        default=None, description="For pct_of_revenue: what % of projected revenue"
    )
    fixed_value_cr: Optional[float] = Field(
        default=None, description="For fixed_amount: the constant value each year (₹ Cr)"
    )
    linked_item: Optional[str] = Field(
        default=None, description="For linked_to_item: the reference line item name"
    )
    linked_rate_pct: Optional[float] = Field(
        default=None, description="For linked_to_item: the rate to apply (e.g. 25.17 for tax)"
    )
    custom_formula: Optional[str] = Field(
        default=None, description="For custom: analyst-written formula string"
    )

    # ── Reasoning & provenance ──
    reasoning: str = Field(description="2-3 sentence explanation for this assumption")
    supporting_facts: List[str] = Field(
        default_factory=list, description="Bullet points with specific data backing this assumption"
    )
    source_urls: List[str] = Field(
        default_factory=list, description="Clickable links to sources"
    )
    confidence: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Confidence score 0.0–1.0"
    )
    historical_cagr_pct: Optional[float] = Field(
        default=None, description="The trailing 3-5 year CAGR for this item (anchor)"
    )
    is_analyst_overridden: bool = Field(
        default=False, description="Set to True if the analyst manually tweaked this assumption"
    )


# ══════════════════════════════════════════════════════════════════════════════
# 2. ASSUMPTIONS PACKAGE
# ══════════════════════════════════════════════════════════════════════════════

class AssumptionsPackage(BaseModel):
    """Complete set of assumptions for analyst review."""

    company_name: str
    base_year: str = Field(description="e.g. 'FY24'")
    projection_horizon_years: int = Field(
        default=3, ge=1, le=10, description="Number of years to project (default: 3)"
    )
    revenue_assumptions: List[Assumption] = Field(default_factory=list)
    expense_assumptions: List[Assumption] = Field(default_factory=list)
    other_assumptions: List[Assumption] = Field(
        default_factory=list,
        description="Tax rate, depreciation, interest, shares outstanding, etc.",
    )
    methodology_notes: List[str] = Field(
        default_factory=list,
        description="High-level notes on the methodology used to generate these assumptions",
    )


# ══════════════════════════════════════════════════════════════════════════════
# 3. MANAGEMENT GUIDANCE SCHEMA
# ══════════════════════════════════════════════════════════════════════════════

class GuidanceItem(BaseModel):
    """A single guidance tracker entry from the NarrativeDecoder."""
    topic: str = ""
    prior_guidance: str = ""
    actual_outcome: str = ""
    management_explanation: str = ""
    credibility: str = Field(default="MEDIUM", description="LOW / MEDIUM / HIGH")
    evidence_prior: str = ""
    evidence_actual: str = ""


class ToneShift(BaseModel):
    """A detected shift in management tone on a topic."""
    topic: str = ""
    prior_tone: str = ""
    current_tone: str = ""
    shift_type: str = ""
    significance: str = Field(default="MEDIUM", description="LOW / MEDIUM / HIGH")


class AnalystDodge(BaseModel):
    """A detected instance of management evading an analyst question."""
    question: str = ""
    management_response: str = ""
    evasion_type: str = ""
    significance: str = "MEDIUM"


class ManagementGuidance(BaseModel):
    """Structured output from NarrativeDecoderV3 — used as verification layer."""

    guidance_tracker: List[GuidanceItem] = Field(default_factory=list)
    tone_shifts: List[ToneShift] = Field(default_factory=list)
    analyst_dodges: List[AnalystDodge] = Field(default_factory=list)
    executive_summary: str = ""
    key_phrases_flagged: List[Dict] = Field(default_factory=list)
    source: str = Field(
        default="unknown",
        description="'rag_narrative_decoder' or 'web_fallback'",
    )


# ══════════════════════════════════════════════════════════════════════════════
# 4. DEVIATION FLAG SCHEMA
# ══════════════════════════════════════════════════════════════════════════════

class DeviationFlag(BaseModel):
    """A single assumption-vs-guidance deviation flag."""
    line_item: str
    your_assumption: str = Field(description="e.g. '8.0% growth'")
    mgmt_said: str = Field(description="What management guided for this topic")
    mgmt_credibility: str = Field(description="LOW / MEDIUM / HIGH")
    deviation_severity: Literal["green", "amber", "red"] = "green"
    note: str = ""


class ToneWarning(BaseModel):
    """A significant tone shift that may affect assumptions."""
    topic: str
    shift: str = Field(description="e.g. 'Optimistic → Cautious'")
    warning: str


class DeviationReport(BaseModel):
    """Complete deviation analysis between assumptions and management guidance."""
    assumption_vs_guidance: List[DeviationFlag] = Field(default_factory=list)
    tone_warnings: List[ToneWarning] = Field(default_factory=list)
    guidance_source: str = "unknown"
    guidance_summary: str = ""
