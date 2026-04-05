"""
Company Overview Schemas
========================
Pydantic output schemas for the company overview node.
Also contains the guardrail validation logic for the generated overview.
"""

from typing import List, Optional, Tuple
from pydantic import BaseModel, Field

# ══════════════════════════════════════════════════════════════════════════════
# 1. PYDANTIC STRUCTURED OUTPUT SCHEMA
# ══════════════════════════════════════════════════════════════════════════════

class CompanyIdentity(BaseModel):
    """Basic identification of the company."""
    full_name: str = Field(description="Full legal name of the company")
    headquarters: str = Field(description="Headquarters location (city, country)")
    founding_year: Optional[str] = Field(default=None, description="Year the company was founded")
    tickers: List[str] = Field(default_factory=list, description="Stock ticker symbols e.g. ['HINDUNILVR.NS']")


class RevenueSegment(BaseModel):
    """A single revenue segment of the company."""
    name: str = Field(description="Name of the revenue segment")
    contribution_pct: Optional[float] = Field(
        default=None,
        description="Approximate revenue contribution as a percentage (0-100). Null if unknown.",
    )
    is_fastest_growing: bool = Field(default=False, description="Whether this is the fastest-growing segment")
    is_most_profitable: bool = Field(default=False, description="Whether this is the most profitable segment")


class CompanyOverviewSchema(BaseModel):
    """Structured business overview for downstream financial analysis."""
    company_identity: CompanyIdentity = Field(description="Basic company identification")
    core_business_model: str = Field(description="How the company generates revenue — products, services, licensing, etc.")
    value_proposition: str = Field(description="Key value proposition and competitive moat")
    revenue_segments: List[RevenueSegment] = Field(description="Major revenue segments with approximate contribution")
    industry_classification: str = Field(description="Industry sector / sub-sector classification")
    top_competitors: List[str] = Field(description="Top 3-5 direct competitors")
    competitive_advantages: List[str] = Field(description="Key competitive advantages")
    key_operational_metrics: List[str] = Field(description="Most important operational metrics for this business (e.g. ARPU, same-store sales)")
    recent_strategic_developments: List[str] = Field(description="Major M&A, partnerships, capex decisions from last 12-18 months")
    risk_factors: List[str] = Field(description="Top 3-5 material risk factors (regulatory, macro, operational, competitive)")
    data_sources: List[str] = Field(
        default_factory=list,
        description="Provenance tracking: list of data sources used (e.g. 'cio_executive_summary', 'prowess_ie_statement', 'tavily_search', 'rag_retrieval')",
    )


# ══════════════════════════════════════════════════════════════════════════════
# 2. GUARDRAIL VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

def validate_overview(overview: CompanyOverviewSchema) -> Tuple[bool, List[str]]:
    """
    Programmatic guardrail checks on the structured LLM output.
    Returns (is_valid, list_of_warnings).
    """
    warnings: List[str] = []

    if not overview.company_identity.full_name or overview.company_identity.full_name.lower() in ("unknown", ""):
        warnings.append("company_identity.full_name is missing or unknown")

    if not overview.core_business_model or len(overview.core_business_model) < 20:
        warnings.append("core_business_model is too short or missing")

    if len(overview.revenue_segments) == 0:
        warnings.append("No revenue_segments identified")

    if len(overview.top_competitors) == 0:
        warnings.append("No competitors identified")

    if len(overview.risk_factors) == 0:
        warnings.append("No risk_factors identified")

    if not overview.industry_classification or overview.industry_classification.lower() in ("unknown", "n/a", ""):
        warnings.append("industry_classification is missing")

    is_valid = len(warnings) == 0
    return is_valid, warnings
