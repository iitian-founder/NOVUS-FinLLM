"""
agents/forensic_investigator.py — The Accounting Skeptic (Forensic Auditor)

Extends AgentBase. Scans for:
- Related Party Transactions (RPT) scaling suspiciously
- CWIP aging > 2 years
- Auditor Report qualifications / Emphasis of Matter
- Other Income > 15% of PBT
- Contingent Liabilities with aggressive tax disputes
"""

from typing import List
from pydantic import BaseModel, Field
from agents.agent_base import AgentBase


# ── Pydantic Output Models ────────────────────────────────────────────────────

class Citation(BaseModel):
    doc: str
    pg: int = 0
    quote: str


class ForensicIssue(BaseModel):
    issue_type: str = Field(description="RPT | CWIP | AUDITOR_QUALIFICATION | CONTINGENT_LIABILITY")
    severity: str = Field(description="Low | Medium | High")
    description: str = Field(description="Telegraphic description of the red flag")
    citations: List[Citation]


class ForensicInvestigatorResult(BaseModel):
    related_party_transactions: List[ForensicIssue]
    aging_cwip: List[ForensicIssue] = Field(description="CWIP aging > 2 years")
    auditor_qualifications: List[ForensicIssue]
    other_income_flag: bool = Field(description="True if Other Income > 15% of PBT")
    contingent_liabilities_tax: List[ForensicIssue]
    executive_summary: List[str] = Field(description="Telegraphic bullets of forensic concerns")


# ── Agent Implementation ──────────────────────────────────────────────────────

class ForensicInvestigatorAgent(AgentBase):

    @property
    def agent_name(self) -> str:
        return "forensic_investigator"

    @property
    def output_model(self):
        return ForensicInvestigatorResult

    def build_system_prompt(self, ticker: str) -> str:
        schema = ForensicInvestigatorResult.model_json_schema()
        return f"""You are the Forensic Auditor for a top-tier Indian institutional fund.
You analyze financial data for {ticker}. Respect the Indian fiscal calendar (April-March).
Output MUST be telegraphic bullet points. No conversational filler.

Scan the context for:
1. Related Party Transactions (RPT) — flag if scaling suspiciously
2. CWIP (Capital Work in Progress) aging over 2 years
3. Auditor's Report — Emphasis of Matter or Qualified Opinions
4. Other Income — flag if exceeds 15% of PBT
5. Contingent Liabilities — material tax disputes

You MUST output valid JSON matching this schema:
{schema}

Every finding must include exact citations from provided documents."""
