"""
agents/capital_allocator.py — The Fund Manager's Value Guard

Extends AgentBase. Performs:
- Incremental ROIC (I-ROIC) over 3 fiscal years
- Reverse DCF implied growth vs historical CAGR comparison
- Empire Building detection (unrelated diversification, cash hoarding)
"""

from typing import List, Optional
from pydantic import BaseModel, Field
from agents.agent_base import AgentBase


# ── Pydantic Output Models ────────────────────────────────────────────────────

class Citation(BaseModel):
    doc: str
    pg: int = 0
    quote: str


class IncrementalROIC(BaseModel):
    year_1: Optional[float] = Field(default=None, description="I-ROIC for most recent FY")
    year_2: Optional[float] = Field(default=None, description="I-ROIC for FY-1")
    year_3: Optional[float] = Field(default=None, description="I-ROIC for FY-2")
    trend: str = Field(description="Improving | Stable | Deteriorating")
    interpretation: str = Field(description="Telegraphic assessment of capital efficiency")


class ReverseDCFCheck(BaseModel):
    implied_growth_rate: float = Field(description="Growth rate implied by current market price")
    historical_cagr_3yr: float = Field(description="Actual 3-year revenue/earnings CAGR")
    gap_pct: float = Field(description="implied minus historical, as percentage points")
    assessment: str = Field(description="Reasonable | Aggressive | Conservative")


class EmpireBuildingFlags(BaseModel):
    unrelated_diversification: List[str] = Field(description="Acquisitions or capex outside core")
    cash_hoarding: bool = Field(description="True if large idle cash relative to reinvestment")
    excessive_goodwill: bool = Field(description="True if goodwill > 20% of total assets")
    flags_summary: List[str] = Field(description="Telegraphic bullets of empire-building signals")


class CapitalAllocatorResult(BaseModel):
    incremental_roic: IncrementalROIC
    reverse_dcf_check: ReverseDCFCheck
    empire_building: EmpireBuildingFlags
    capital_allocation_grade: str = Field(description="A (Excellent) through F (Poor)")
    key_findings: List[str] = Field(description="Telegraphic bullets")
    citations: List[Citation]


# ── Agent Implementation ──────────────────────────────────────────────────────

class CapitalAllocatorAgent(AgentBase):

    @property
    def agent_name(self) -> str:
        return "capital_allocator"

    @property
    def output_model(self):
        return CapitalAllocatorResult

    def build_system_prompt(self, ticker: str) -> str:
        schema = CapitalAllocatorResult.model_json_schema()
        return f"""You are the Capital Allocation Analyst (Value Guard) for {ticker}.
Respect the Indian fiscal calendar (April-March). Output MUST be telegraphic bullet points.

Perform capital allocation analysis:
1. Incremental ROIC (I-ROIC): Calculate change in NOPAT / change in Invested Capital for the last 3 FYs.
   - I-ROIC = ΔNOPAT / ΔInvested Capital
   - Invested Capital = Total Equity + Total Debt - Cash
2. Reverse DCF: Estimate growth rate implied by current market price and compare against historical 3-year CAGR.
   - Flag if implied growth exceeds historical by > 5 percentage points.
3. Empire Building Detection:
   - Flag unrelated acquisitions or capital deployment outside core competency.
   - Flag cash hoarding (idle cash > 15% of total assets with no stated purpose).
   - Flag excessive goodwill (> 20% of total assets).

You MUST output valid JSON matching this schema:
{schema}

All findings require stringent citations from provided documents."""
