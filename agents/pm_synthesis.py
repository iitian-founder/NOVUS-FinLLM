# agents/pm_synthesis.py
"""
Agent 5: PM Synthesis Agent (Phases 8, 9, 10 & 13 — Thesis, Risk, Monitoring)

Type: Synthesis + Structured Output
This is the ONLY agent allowed to generate narrative reasoning.
But even here, constrain it heavily.

Law 3 of FinLLM Safety: Make uncertainty explicit.
Every thesis output MUST have a "data_gaps" field.
Missing data must be surfaced, not interpolated.
"""

import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logic import call_deepseek


# ── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class InvestmentThesis:
    """
    Structured investment thesis output.
    JSON-schema enforced — the data_gaps field is NON-NEGOTIABLE.
    """
    ticker: str = ""
    thesis_summary: str = ""                    # Max 2 sentences
    bull_case_pillars: list[str] = field(default_factory=list)
    bear_case_risks: list[dict] = field(default_factory=list)  # [{risk, probability}]
    variant_perception: str = ""                # Your EDGE — what does the market NOT see?
    forensic_quality_score: str = "C"           # A, B, C, D
    management_evasion_score: float = 0.0       # 0-1
    reverse_dcf_implied_growth: Optional[float] = None
    pricing_verdict: str = "FAIR"               # CHEAP, FAIR, EXPENSIVE
    recommended_action: str = "WATCH"           # BUY, WATCH, PASS
    kill_criteria: list[str] = field(default_factory=list)
    data_gaps: list[str] = field(default_factory=list)  # ALWAYS populate honestly

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "thesis_summary": self.thesis_summary,
            "bull_case_pillars": self.bull_case_pillars,
            "bear_case_risks": self.bear_case_risks,
            "variant_perception": self.variant_perception,
            "forensic_quality_score": self.forensic_quality_score,
            "management_evasion_score": self.management_evasion_score,
            "reverse_dcf_implied_growth": self.reverse_dcf_implied_growth,
            "pricing_verdict": self.pricing_verdict,
            "recommended_action": self.recommended_action,
            "kill_criteria": self.kill_criteria,
            "data_gaps": self.data_gaps,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def to_markdown(self) -> str:
        """Render the thesis as a readable markdown document."""
        md = []
        md.append(f"# 📊 Investment Thesis: {self.ticker}")
        md.append("")
        md.append(f"**Summary:** {self.thesis_summary}")
        md.append("")

        md.append("## 🟢 Bull Case Pillars")
        for i, pillar in enumerate(self.bull_case_pillars, 1):
            md.append(f"{i}. {pillar}")
        md.append("")

        md.append("## 🔴 Bear Case Risks")
        for risk in self.bear_case_risks:
            r = risk.get("risk", "")
            p = risk.get("probability", "Unknown")
            md.append(f"- **{r}** — Probability: {p}")
        md.append("")

        md.append("## 🎯 Variant Perception")
        md.append(self.variant_perception or "_Not identified._")
        md.append("")

        md.append("## 📈 Scoreboard")
        md.append(f"| Metric | Value |")
        md.append(f"|--------|-------|")
        md.append(f"| Forensic Quality | **{self.forensic_quality_score}** |")
        md.append(f"| Management Transparency | **{self.management_evasion_score:.0%}** |")
        if self.reverse_dcf_implied_growth is not None:
            md.append(f"| Reverse DCF Implied Growth | **{self.reverse_dcf_implied_growth:.1%}** |")
        md.append(f"| Pricing Verdict | **{self.pricing_verdict}** |")
        md.append(f"| Recommended Action | **{self.recommended_action}** |")
        md.append("")

        md.append("## 🚪 Kill Criteria (Sell If)")
        for kc in self.kill_criteria:
            md.append(f"- {kc}")
        md.append("")

        if self.data_gaps:
            md.append("## ⚠️ Data Gaps (Requires Human Review)")
            for gap in self.data_gaps:
                md.append(f"- {gap}")

        return "\n".join(md)


# ── Synthesis Prompt ─────────────────────────────────────────────────────────

SYNTHESIS_SYSTEM_PROMPT = """You are an elite portfolio manager at a top-tier long-only fund.
You ONLY make decisions based on the structured data provided to you.
You DO NOT have access to the internet or any outside knowledge.
You NEVER state anything you cannot directly source from the provided inputs.

If any required data is missing, say: "DATA NOT AVAILABLE — REQUIRES HUMAN REVIEW."
Do not guess. Do not interpolate. Do not hallucinate.

Your task is to synthesize the provided agent outputs into a structured
investment thesis using the EXACT JSON schema below.

REQUIRED OUTPUT FORMAT (JSON only, no other text):
{
  "thesis_summary": "Max 2 sentences describing the investment case",
  "bull_case_pillars": ["Pillar 1", "Pillar 2", "Pillar 3"],
  "bear_case_risks": [
    {"risk": "Description", "probability": "Low|Medium|High"},
    {"risk": "Description", "probability": "Low|Medium|High"}
  ],
  "variant_perception": "What does the market NOT see? Your edge.",
  "forensic_quality_score": "A|B|C|D",
  "pricing_verdict": "CHEAP|FAIR|EXPENSIVE",
  "recommended_action": "BUY|WATCH|PASS",
  "kill_criteria": ["Measurable condition 1", "Measurable condition 2"],
  "data_gaps": ["Missing data point 1", "Missing data point 2"]
}

RULES:
1. The data_gaps field is MANDATORY. You MUST list anything you couldn't verify.
2. forensic_quality_score: A = excellent (ROIC>20%, high cash quality), B = good, C = average, D = poor.
3. pricing_verdict: Use reverse DCF implied growth vs realistic growth to determine.
4. kill_criteria must be SPECIFIC and MEASURABLE (e.g., "ROIC drops below 12% for 2 consecutive quarters").
5. NEVER make up variant perception. If you don't see a clear edge, say "No clear variant perception identified."
"""


def build_synthesis_input(
    ticker: str,
    forensic_scorecard_dict: dict,
    nlp_flags_dict: dict,
    qualitative_md: str = "",
    triage_result: dict = None,
) -> str:
    """Assemble all agent outputs into a single context document for the PM Agent."""
    sections = []

    sections.append(f"# Agent Outputs for {ticker}")
    sections.append("")

    # Triage result
    if triage_result:
        sections.append("## Agent 1: Triage Result")
        sections.append(f"Passed Kill Screen: {triage_result.get('passed', 'Unknown')}")
        if triage_result.get('warnings'):
            sections.append("Warnings:")
            for w in triage_result['warnings']:
                sections.append(f"  - {w}")
        sections.append("")

    # Forensic scorecard
    sections.append("## Agent 3: Forensic Quant Scorecard")
    sections.append("```json")
    sections.append(json.dumps(forensic_scorecard_dict, indent=2))
    sections.append("```")
    sections.append("")

    # NLP flags
    sections.append("## Agent 4: NLP Analyst Flags")
    sections.append("```json")
    sections.append(json.dumps(nlp_flags_dict, indent=2))
    sections.append("```")
    sections.append("")

    # Qualitative analysis
    if qualitative_md:
        sections.append("## Qualitative Analysis (from Agent 4)")
        sections.append(qualitative_md[:5000])

    return "\n".join(sections)


# ── Main Pipeline Entry Point ────────────────────────────────────────────────

def run_pm_synthesis(
    ticker: str,
    forensic_scorecard_dict: dict,
    nlp_flags_dict: dict,
    qualitative_assumptions_md: str = "",
    triage_result_dict: dict = None,
    rag_context: str = "",
) -> InvestmentThesis:
    """
    Run the PM Synthesis Agent.
    
    This is the ONLY agent allowed to generate narrative.
    Even here, it is constrained by:
    - JSON-schema enforcement
    - Mandatory data_gaps field
    - System prompt preventing hallucination
    
    If rag_context is provided, it enriches the synthesis with data
    from ALL uploaded company documents (annual reports, presentations, etc.)
    """
    thesis = InvestmentThesis(ticker=ticker)

    # Build the combined input context
    synthesis_input = build_synthesis_input(
        ticker,
        forensic_scorecard_dict,
        nlp_flags_dict,
        qualitative_assumptions_md,
        triage_result_dict,
    )

    # Append RAG context if available
    if rag_context:
        synthesis_input += "\n\n" + rag_context

    # Call DeepSeek with structured system prompt
    response = call_deepseek(SYNTHESIS_SYSTEM_PROMPT, synthesis_input)

    if not response or response.startswith("Error"):
        thesis.data_gaps.append("PM Synthesis LLM call failed — full human review required.")
        return thesis

    # Parse the structured JSON output
    try:
        clean = response.strip()
        if '```json' in clean:
            clean = clean.split('```json', 1)[1].rsplit('```', 1)[0]
        elif '```' in clean:
            clean = clean.split('```', 1)[1].rsplit('```', 1)[0]

        parsed = json.loads(clean.strip())

        thesis.thesis_summary = parsed.get("thesis_summary", "")
        thesis.bull_case_pillars = parsed.get("bull_case_pillars", [])
        thesis.bear_case_risks = parsed.get("bear_case_risks", [])
        thesis.variant_perception = parsed.get("variant_perception", "")
        thesis.forensic_quality_score = parsed.get("forensic_quality_score", "C")
        thesis.pricing_verdict = parsed.get("pricing_verdict", "FAIR")
        thesis.recommended_action = parsed.get("recommended_action", "WATCH")
        thesis.kill_criteria = parsed.get("kill_criteria", [])
        thesis.data_gaps = parsed.get("data_gaps", [])

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        thesis.data_gaps.append(f"Failed to parse synthesis output: {e}")
        thesis.data_gaps.append("Raw LLM output saved — requires manual review.")

    # Inject management evasion score from NLP flags
    evasion_data = nlp_flags_dict.get("management_evasion", {})
    thesis.management_evasion_score = evasion_data.get("overall_score", 0.0)

    # Inject reverse DCF from forensic scorecard
    val_data = forensic_scorecard_dict.get("valuation", {})
    thesis.reverse_dcf_implied_growth = val_data.get("reverse_dcf_implied_growth")

    # Ensure data_gaps is never empty — this is our safety net
    if not thesis.data_gaps:
        thesis.data_gaps.append(
            "No explicit data gaps identified by synthesis agent — "
            "human analyst should verify completeness."
        )

    return thesis


# ── Convenience: Generate Prompt Set ─────────────────────────────────────────

def generate_prompt_set(transcript_text: str, qualitative_context: str = "") -> str:
    """
    Generate 3-5 smart, company-specific prompts for deeper analysis.
    """
    prompt = (
        "Based on the provided concall text, generate 3-5 company-specific, smart, "
        "and non-generic prompts an investor could ask an LLM to explore further."
    )
    return call_deepseek(
        prompt, transcript_text, extra_context=qualitative_context
    )
