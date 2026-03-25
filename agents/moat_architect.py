"""
agents/moat_architect.py — The Industry Strategist

Extends AgentBase. Performs:
- Volume vs Value growth analysis
- Industry benchmarking against GST/Rural demand data
- Market Share trend identification (gains vs losses)
- Porter's Five Forces assessment for pricing power sustainability
"""

from typing import List
from pydantic import BaseModel, Field
from agents.agent_base import AgentBase


# ── Pydantic Output Models ────────────────────────────────────────────────────

class Citation(BaseModel):
    doc: str
    pg: int = 0
    quote: str


class PorterForces(BaseModel):
    threat_of_new_entrants: str
    bargaining_power_of_suppliers: str
    bargaining_power_of_buyers: str
    threat_of_substitutes: str
    industry_rivalry: str


class MoatArchitectResult(BaseModel):
    volume_vs_value_growth: str = Field(description="Price hikes vs actual volume growth analysis")
    industry_benchmarking: str = Field(description="Compared against GST/Rural demand data")
    market_share_trend: str = Field(description="Gaining or losing share")
    porters_five_forces: PorterForces
    competitive_advantage_summary: List[str] = Field(description="Telegraphic bullets on moat and pricing power")
    citations: List[Citation]


# ── Agent Implementation ──────────────────────────────────────────────────────

class MoatArchitectAgent(AgentBase):

    @property
    def agent_name(self) -> str:
        return "moat_architect"

    @property
    def output_model(self):
        return MoatArchitectResult

    def build_system_prompt(self, ticker: str) -> str:
        schema = MoatArchitectResult.model_json_schema()
        return f"""You are the Industry Strategist (Moat Architect) for {ticker}.
Respect the Indian fiscal calendar (April-March). Output MUST be telegraphic bullet points.

Perform strategic industry analysis:
1. Analyze 'Volume vs. Value' growth — distinguish price hikes from real demand
2. Benchmark against industry average GST/Rural demand indicators
3. Identify competitive positioning (Market Share Gains vs. Losses)
4. Apply Porter's Five Forces to assess pricing power sustainability

You MUST output valid JSON matching this schema:
{schema}

All findings require stringent citations from provided documents."""
