"""
agents/fsa_quant.py — The Mathematical Analyst

Extends AgentBase. Performs:
- 3-step DuPont Analysis (ROE decomposition)
- Cash Conversion Cycle (CCC)
- EBITDA-to-OCF conversion ratio
- Earnings Quality flag (PAT growth vs OCF growth)
"""

from typing import List
from pydantic import BaseModel, Field
from agents.agent_base import AgentBase


# ── Pydantic Output Models ────────────────────────────────────────────────────

class Citation(BaseModel):
    doc: str = Field(description="Source document filename")
    pg: int = Field(default=0, description="Page number")
    quote: str = Field(description="Exact quote from the document")


class DuPontAnalysis(BaseModel):
    net_profit_margin: float = Field(description="Net Income / Sales")
    asset_turnover: float = Field(description="Sales / Total Assets")
    equity_multiplier: float = Field(description="Total Assets / Shareholders' Equity")
    roe: float = Field(description="Calculated Return on Equity = margin × turnover × multiplier")


class CashConversionCycle(BaseModel):
    days_inventory: float
    days_receivables: float
    days_payables: float
    ccc_days: float = Field(description="DIO + DSO - DPO")


class FSAQuantResult(BaseModel):
    dupont_analysis: DuPontAnalysis
    cash_conversion_cycle: CashConversionCycle
    ebitda_to_ocf_ratio: float = Field(description="EBITDA / Operating Cash Flow")
    earnings_quality_flag: bool = Field(description="True if PAT growth >> OCF growth")
    findings: List[str] = Field(description="Telegraphic bullet points")
    citations: List[Citation]


# ── Agent Implementation ──────────────────────────────────────────────────────

class FSAQuantAgent(AgentBase):

    @property
    def agent_name(self) -> str:
        return "fsa_quant"

    @property
    def output_model(self):
        return FSAQuantResult

    def build_system_prompt(self, ticker: str) -> str:
        schema = FSAQuantResult.model_json_schema()
        return f"""You are the FSA Quant Analyst for a top-tier Indian institutional fund.
You analyze financial data for {ticker}. Respect the Indian fiscal calendar (April-March).
Output MUST be telegraphic bullet points. No conversational filler.

Perform these calculations based on the provided context:
1. 3-step DuPont Analysis: ROE = (Net Income/Sales) × (Sales/Total Assets) × (Total Assets/Equity)
2. Cash Conversion Cycle: DIO + DSO - DPO
3. EBITDA-to-OCF conversion ratio
4. Earnings Quality Flag: True if PAT growth materially exceeds OCF growth

You MUST output valid JSON matching this schema:
{schema}

Every finding must include a citation with exact document quotes."""
