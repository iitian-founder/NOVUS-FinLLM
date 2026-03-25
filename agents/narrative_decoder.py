"""
agents/narrative_decoder.py — The Concall & Guidance Expert

Extends AgentBase. Performs:
- Management Guidance vs Actuals mapping (Q3 → Q4)
- Language Drift Analysis (optimistic → cautious tone shifts)
- Analyst Dodging detection (non-answers to specific questions)
"""

from typing import List
from pydantic import BaseModel, Field
from agents.agent_base import AgentBase


# ── Pydantic Output Models ────────────────────────────────────────────────────

class Citation(BaseModel):
    doc: str
    pg: int = 0
    quote: str


class Discrepancy(BaseModel):
    topic: str
    q3_guidance: str
    q4_actuals: str
    discrepancy_score: int = Field(description="1-10 severity of miss/drift")
    citations: List[Citation]


class NarrativeDecoderResult(BaseModel):
    guidance_vs_actuals: List[Discrepancy]
    language_drift_flags: List[str] = Field(description="Shifts from Optimistic/Volume-led to Challenging/Price-sensitive")
    analyst_dodging_detected: List[str] = Field(description="Instances of management non-answers")
    key_takeaways: List[str] = Field(description="Telegraphic bullets summarizing management tone")


# ── Agent Implementation ──────────────────────────────────────────────────────

class NarrativeDecoderAgent(AgentBase):

    @property
    def agent_name(self) -> str:
        return "narrative_decoder"

    @property
    def output_model(self):
        return NarrativeDecoderResult

    def build_system_prompt(self, ticker: str) -> str:
        schema = NarrativeDecoderResult.model_json_schema()
        return f"""You are the Narrative Decoder for {ticker}.
Respect the Indian fiscal calendar (April-March). Output MUST be telegraphic bullet points.

Analyze Q3 vs Q4 transcripts and context to:
1. Map Management 'Guidance' (promises made) against 'Actuals' (results delivered)
2. Perform 'Language Drift Analysis' — detect tone shifts (optimistic/volume-led → challenging/price-sensitive)
3. Flag 'Analyst Dodging' — non-answers to specific margin or rural-demand questions

You MUST output valid JSON matching this schema:
{schema}

Ensure quotes in citations map exactly to the provided context."""
