# agents/nlp_analyst.py
"""
Agent 4: NLP Analyst Agent (Phases 3, 4 & 5 — Industry, Moat, Management)

Type: RAG + Structured Reasoning
This is where most naive FinLLMs fail.

Key design insight: The LLM's job is NOT to judge. Its job is to retrieve,
compare, and classify. Keep narrative generation to the minimum possible.
Structure always beats open-ended generation in financial tasks.

Danger Zones:
- Do NOT ask an LLM: "Does this company have a moat?" — it will echo the
  annual report's own marketing.
- Do NOT ask an LLM: "Is this management trustworthy?" — it will read the
  polished management script and say yes.
"""

import json
import re
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logic import call_deepseek, call_gemini


# ── Deduplication Helper ─────────────────────────────────────────────────────

def deduplicate_markdown(text: str) -> str:
    """
    Remove duplicate lines/bullets from LLM markdown output.
    Gemini sometimes repeats the same point dozens of times
    when the source transcript has repetitive sections.
    """
    if not text:
        return text

    lines = text.split('\n')
    seen = set()
    deduped = []

    for line in lines:
        # Normalize for comparison: strip whitespace, bullets, numbering
        normalized = re.sub(r'^[\s\-\*•\d\.]+', '', line).strip().lower()

        # Keep empty lines and headers (they structure the document)
        if not normalized or line.strip().startswith('#'):
            deduped.append(line)
            continue

        # Skip if we've seen this exact content before
        if normalized in seen:
            continue

        seen.add(normalized)
        deduped.append(line)

    return '\n'.join(deduped)


# ── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class ManagementEvasionScore:
    """
    Structured scoring of management communication quality.
    Based on earnings call Q&A analysis ONLY — never the opening statement.
    """
    question_dodge_rate: float = 0.0         # % of questions deflected/ignored
    accountability_ratio: float = 1.0        # Positive self-attribution / Negative external-attribution
    guidance_track_record: float = 0.0       # % of guidance met/exceeded
    new_risk_disclosure_count: int = 0       # New risk factors in recent quarters
    response_classifications: list[dict] = field(default_factory=list)
    overall_score: float = 0.0              # 0-1, higher = more transparent
    red_flags: list[str] = field(default_factory=list)


@dataclass
class MoatVerification:
    """
    Adversarial RAG-based moat verification result.
    """
    claimed_advantages: list[str] = field(default_factory=list)
    verdicts: list[dict] = field(default_factory=list)  # [{claim, verdict, evidence}]
    overall_moat_strength: str = "UNVERIFIABLE"  # "STRONG", "MODERATE", "WEAK", "UNVERIFIABLE"
    data_gaps: list[str] = field(default_factory=list)


@dataclass
class NLPAnalysisResult:
    """Output of the NLP Analyst Agent."""
    ticker: str
    management_evasion: ManagementEvasionScore = field(default_factory=ManagementEvasionScore)
    moat_verification: MoatVerification = field(default_factory=MoatVerification)
    industry_analysis: str = ""
    business_model_summary: str = ""
    quarterly_updates: str = ""
    management_commentary: str = ""
    risks: str = ""
    data_gaps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "management_evasion": {
                "question_dodge_rate": self.management_evasion.question_dodge_rate,
                "accountability_ratio": self.management_evasion.accountability_ratio,
                "overall_score": self.management_evasion.overall_score,
                "red_flags": self.management_evasion.red_flags,
                "classifications": self.management_evasion.response_classifications,
            },
            "moat_verification": {
                "claimed_advantages": self.moat_verification.claimed_advantages,
                "verdicts": self.moat_verification.verdicts,
                "overall_strength": self.moat_verification.overall_moat_strength,
            },
            "data_gaps": self.data_gaps,
        }


# ── Management Evasion Tracker ───────────────────────────────────────────────

QA_CLASSIFICATION_PROMPT = """You are analyzing the Q&A section of an earnings call. Your task is ONLY to
classify each management response using the following labels:
[DIRECT_ANSWER | PARTIAL_ANSWER | DEFLECTION | TOPIC_CHANGE | IGNORED]

Do NOT evaluate the quality of the answer. Do NOT judge truthfulness.
Your ONLY job is structural classification.

For each question-answer pair, identify:
1. The analyst firm (if mentioned)
2. A brief summary of the question (max 15 words)
3. The response classification label

Return a JSON array ONLY, no other text:
[
  {
    "question_id": 1,
    "analyst_firm": "Morgan Stanley" or "Unknown",
    "question_summary": "Brief summary of what was asked",
    "response_label": "DIRECT_ANSWER"
  }
]

Q&A Transcript:
"""


def score_management_evasion(qa_text: str) -> ManagementEvasionScore:
    """
    Score management transparency from earnings call Q&A sections.
    
    Metrics:
    1. Question Dodge Rate (QDR): QDR > 30% = red flag
    2. Accountability Ratio: Score < 0.5 = low accountability culture
    3. Response classification via structured LLM prompt
    
    IMPORTANT: Feed Q&A sections ONLY. Opening statement excluded.
    An LLM fed a full earnings transcript will call every CEO "confident and focused."
    """
    score = ManagementEvasionScore()

    if not qa_text or len(qa_text.strip()) < 100:
        return score

    # Use LLM for structural classification ONLY
    prompt = QA_CLASSIFICATION_PROMPT
    response = call_deepseek(prompt, qa_text[:8000])  # Limit context size

    if not response or response.startswith("Error"):
        return score

    # Parse the classification response
    try:
        clean = response.strip()
        if '```json' in clean:
            clean = clean.split('```json', 1)[1].rsplit('```', 1)[0]
        elif '```' in clean:
            clean = clean.split('```', 1)[1].rsplit('```', 1)[0]

        classifications = json.loads(clean.strip())

        if isinstance(classifications, list):
            score.response_classifications = classifications

            total = len(classifications)
            if total > 0:
                deflections = sum(
                    1 for c in classifications
                    if c.get("response_label") in ("DEFLECTION", "TOPIC_CHANGE", "IGNORED")
                )
                score.question_dodge_rate = round(deflections / total, 2)

                # Flag if QDR > 30%
                if score.question_dodge_rate > 0.30:
                    score.red_flags.append(
                        f"Question Dodge Rate = {score.question_dodge_rate:.0%} "
                        f"({deflections}/{total} questions deflected/ignored)"
                    )

                # Overall transparency score (inverted QDR)
                score.overall_score = round(1.0 - score.question_dodge_rate, 2)

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"[NLP Analyst] Failed to parse Q&A classifications: {e}")

    return score


# ── Adversarial Moat Verification ────────────────────────────────────────────

MOAT_VERIFICATION_PROMPT = """You are a skeptical analyst tasked with evaluating competitive advantages.

Based on the company's filings and transcript, identify the company's CLAIMED competitive advantages.
Then, for each claim, assess whether the available data SUPPORTS or CONTRADICTS it.

Rules:
1. Only use information explicitly present in the provided text.
2. If you cannot find data to verify a claim, say: "UNVERIFIABLE".
3. Do NOT guess or infer advantages not mentioned in the text.
4. Be skeptical — companies overstate their moats in annual reports.

Return a JSON object ONLY:
{
  "claimed_advantages": [
    {
      "claim": "Description of claimed advantage",
      "type": "BRAND | SWITCHING_COST | NETWORK_EFFECT | COST_ADVANTAGE | REGULATORY | DISTRIBUTION | INTANGIBLE",
      "verdict": "SUPPORTED | CONTRADICTED | PARTIALLY_SUPPORTED | UNVERIFIABLE",
      "evidence": "Brief evidence from the text supporting or contradicting the claim",
      "confidence": 0.0 to 1.0
    }
  ],
  "overall_moat_strength": "STRONG | MODERATE | WEAK | UNVERIFIABLE"
}

Company filings and transcript:
"""


def verify_moat_claims(transcript_text: str, financial_data_summary: str = "") -> MoatVerification:
    """
    Adversarial RAG approach to moat verification.
    
    Do NOT ask an LLM: "Does Company A have a cost advantage?"
    It will summarize Company A's annual report claims. That's the PR department talking.
    
    Correct approach: Force the model to identify claims and then evaluate
    each against evidence. "UNVERIFIABLE" is always preferable to a guess.
    """
    result = MoatVerification()

    combined_text = transcript_text
    if financial_data_summary:
        combined_text += f"\n\n---\n\nFinancial Data Summary:\n{financial_data_summary}"

    response = call_deepseek(MOAT_VERIFICATION_PROMPT, combined_text[:12000])

    if not response or response.startswith("Error"):
        result.data_gaps.append("LLM failed to process moat verification")
        return result

    try:
        clean = response.strip()
        if '```json' in clean:
            clean = clean.split('```json', 1)[1].rsplit('```', 1)[0]
        elif '```' in clean:
            clean = clean.split('```', 1)[1].rsplit('```', 1)[0]

        parsed = json.loads(clean.strip())

        for adv in parsed.get("claimed_advantages", []):
            result.claimed_advantages.append(adv.get("claim", ""))
            result.verdicts.append({
                "claim": adv.get("claim", ""),
                "type": adv.get("type", "UNKNOWN"),
                "verdict": adv.get("verdict", "UNVERIFIABLE"),
                "evidence": adv.get("evidence", ""),
                "confidence": adv.get("confidence", 0.0),
            })

        result.overall_moat_strength = parsed.get("overall_moat_strength", "UNVERIFIABLE")

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        result.data_gaps.append(f"Failed to parse moat verification: {e}")

    return result


# ── Qualitative Analysis Prompts (from existing logic.py PROMPTS) ────────────

PROMPTS = {
    "business_model": (
        "You are an equity research analyst. Summarize the company's business model "
        "in simple, investor-friendly terms based on the provided text. Include these "
        'exact markdown headings: "📌 Core Products & Services", '
        '"🎯 Target Markets / Customers", "💸 Revenue Model & Geography", '
        'and "📈 Scale & Competitive Positioning". '
        "IMPORTANT: Do NOT repeat any point. Each bullet must be unique."
    ),
    "key_quarterly_updates": (
        "Extract the 5-7 most important operational or financial updates from this "
        "concall text. Focus on: Growth drivers, Orders/capacity/margins, Strategy "
        "changes, and direct Quotes or signals from management. Present as a bulleted "
        "list in Markdown. IMPORTANT: Each bullet point must be UNIQUE — do NOT repeat "
        "any point even if it appears multiple times in the transcript."
    ),
    "management_commentary": (
        "Summarize management's guidance and tone for the next 1-2 quarters from the "
        'provided text. Format your answer in Markdown under these exact headings: '
        '"🔹 Forward-Looking Statements", "🔹 Management Tone & Confidence" '
        "(classify tone as Optimistic/Cautious/Neutral and support with quotes), "
        'and "🔹 Capex / Risk / Guidance Highlights". '
        "IMPORTANT: Do NOT repeat any point. Consolidate similar points into one."
    ),
    "risks_uncertainties": (
        "List the key risks or uncertainties based on the concall text. Categorize "
        'them under these exact Markdown headings if possible: "Execution Risks", '
        '"Demand-side or Macro Risks", and "Regulatory / External Risks". '
        "CRITICAL RULE: Each risk must appear EXACTLY ONCE. Do NOT duplicate "
        "any risk point, even if the source text mentions it multiple times. "
        "Limit to 3-5 risks per category maximum."
    ),
    "prompt_set": (
        "Based on the provided concall text, generate 3-5 company-specific, smart, "
        "and non-generic prompts an investor could ask an LLM to explore further. "
        "Each prompt must be unique."
    ),
}


# ── Main Pipeline Entry Point ────────────────────────────────────────────────

def run_nlp_analysis(
    ticker: str,
    transcript_text: str,
    qa_sections: list[str] = None,
    financial_data_summary: str = "",
    rag_context: str = "",
) -> NLPAnalysisResult:
    """
    Run the full NLP Analyst pipeline.
    
    Steps:
    1. Business model summary (Gemini — extraction task)
    2. Key quarterly updates (Gemini — extraction task)
    3. Management commentary (Gemini — extraction task)
    4. Risks & uncertainties (Gemini — extraction task)
    5. Management evasion scoring (DeepSeek — Q&A classification only)
    6. Adversarial moat verification (DeepSeek — structured reasoning)
    
    If rag_context is provided, it is passed as extra_context to all Gemini calls
    so that the model can reference information from ALL uploaded documents.
    """
    result = NLPAnalysisResult(ticker=ticker)

    # Step 1-4: Qualitative extraction via Gemini (best for extraction tasks)
    # All outputs go through deduplicate_markdown() to remove LLM repetition
    # RAG context enriches analysis with data from annual reports, presentations, etc.
    result.business_model_summary = deduplicate_markdown(call_gemini(
        PROMPTS["business_model"], transcript_text,
        extra_context=rag_context if rag_context else None,
    ))
    result.quarterly_updates = deduplicate_markdown(call_gemini(
        PROMPTS["key_quarterly_updates"], transcript_text,
        extra_context=rag_context if rag_context else None,
    ))
    result.management_commentary = deduplicate_markdown(call_gemini(
        PROMPTS["management_commentary"], transcript_text,
        extra_context=rag_context if rag_context else None,
    ))
    result.risks = deduplicate_markdown(call_gemini(
        PROMPTS["risks_uncertainties"], transcript_text,
        extra_context=rag_context if rag_context else None,
    ))

    # Step 5: Management evasion scoring (Q&A sections only!)
    if qa_sections:
        qa_combined = "\n\n---\n\n".join(qa_sections)
        result.management_evasion = score_management_evasion(qa_combined)
    else:
        result.data_gaps.append(
            "No Q&A sections available — management evasion scoring skipped."
        )

    # Step 6: Adversarial moat verification
    result.moat_verification = verify_moat_claims(
        transcript_text, financial_data_summary
    )

    return result
