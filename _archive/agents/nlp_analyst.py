# agents/nlp_analyst.py (v2)
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

v2 Changelog (all from audit):
  FIX 1:  Four Gemini calls run concurrently via ThreadPoolExecutor
  FIX 2:  Context truncation logged in data_gaps with char counts
  FIX 3:  All LLM calls wrapped in _safe_llm_call — catches raises + "Error" prefix
  FIX 4:  Removed sys.path manipulation — proper import
  FIX 5:  JSON fence stripping uses shared _strip_llm_json_fences utility
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional, Callable

# FIX 4: Proper import — no sys.path hacking.
# Requires PYTHONPATH or package __init__.py to include project root.
from llm_clients import call_deepseek, call_gemini


# ── FIX 5: Shared JSON Fence Stripping ───────────────────────────────────────

def _strip_llm_json_fences(text: str) -> str:
    """Remove markdown JSON fences from LLM output."""
    clean = text.strip()
    if '```json' in clean:
        clean = clean.split('```json', 1)[1].rsplit('```', 1)[0]
    elif '```' in clean:
        clean = clean.split('```', 1)[1].rsplit('```', 1)[0]
    return clean.strip()


# ── FIX 3: Safe LLM Call Wrapper ─────────────────────────────────────────────
#
# The v1 error convention assumed LLM functions return "Error: ..." strings on
# failure and never raise. But call_gemini and call_deepseek are wrappers around
# HTTP APIs — they can raise on network timeouts, JSON decode failures,
# auth errors, etc. This wrapper catches both conventions.

def _safe_llm_call(
    llm_fn: Callable,
    *args,
    label: str = "LLM call",
    **kwargs,
) -> tuple[Optional[str], Optional[str]]:
    """
    Call an LLM function safely. Returns (response, error).

    - If the call succeeds and returns content: (response, None)
    - If the call returns an "Error" string: (None, error_message)
    - If the call raises an exception: (None, error_message)
    - If the call returns empty/None: (None, "empty response")
    """
    try:
        response = llm_fn(*args, **kwargs)
        if not response:
            return None, f"{label}: LLM returned empty response"
        if isinstance(response, str) and response.startswith("Error"):
            return None, f"{label}: {response[:300]}"
        return response, None
    except Exception as e:
        return None, f"{label}: {type(e).__name__} — {e}"


# ── FIX 2: Truncation with Logging ──────────────────────────────────────────

def _truncate_with_warning(
    text: str,
    max_chars: int,
    label: str,
    data_gaps: list[str],
) -> str:
    """
    Truncate text to max_chars. If truncation occurs, append a warning
    to data_gaps so the analyst knows the analysis was based on partial data.
    """
    if len(text) <= max_chars:
        return text

    data_gaps.append(
        f"{label}: Input truncated from {len(text):,} to {max_chars:,} chars "
        f"({100 - (max_chars / len(text) * 100):.0f}% discarded). "
        f"Scoring is based on partial data."
    )
    return text[:max_chars]


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
        normalized = re.sub(r'^[\s\-\*•\d\.]+', '', line).strip().lower()

        if not normalized or line.strip().startswith('#'):
            deduped.append(line)
            continue

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
    question_dodge_rate: float = 0.0
    accountability_ratio: float = 1.0
    guidance_track_record: float = 0.0
    new_risk_disclosure_count: int = 0
    response_classifications: list[dict] = field(default_factory=list)
    overall_score: float = 0.0
    red_flags: list[str] = field(default_factory=list)
    # FIX 2: Track how much of the Q&A was actually analysed
    chars_analysed: int = 0
    chars_available: int = 0


@dataclass
class MoatVerification:
    """Adversarial RAG-based moat verification result."""
    claimed_advantages: list[str] = field(default_factory=list)
    verdicts: list[dict] = field(default_factory=list)
    overall_moat_strength: str = "UNVERIFIABLE"
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
                "chars_analysed": self.management_evasion.chars_analysed,
                "chars_available": self.management_evasion.chars_available,
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

# FIX 2: Configurable limits
QA_MAX_CHARS = 8000
MOAT_MAX_CHARS = 12000


def score_management_evasion(
    qa_text: str,
    data_gaps: list[str],
) -> ManagementEvasionScore:
    """
    Score management transparency from earnings call Q&A sections.

    IMPORTANT: Feed Q&A sections ONLY. Opening statement excluded.
    """
    score = ManagementEvasionScore()

    if not qa_text or len(qa_text.strip()) < 100:
        return score

    # FIX 2: Track how much text we're actually analysing
    score.chars_available = len(qa_text)
    truncated_text = _truncate_with_warning(
        qa_text, QA_MAX_CHARS, "Management evasion scoring", data_gaps,
    )
    score.chars_analysed = len(truncated_text)

    # FIX 3: Safe LLM call
    response, error = _safe_llm_call(
        call_deepseek, QA_CLASSIFICATION_PROMPT, truncated_text,
        label="Q&A classification",
    )
    if error:
        data_gaps.append(error)
        return score

    try:
        clean = _strip_llm_json_fences(response)
        classifications = json.loads(clean)

        if isinstance(classifications, list):
            score.response_classifications = classifications
            total = len(classifications)
            if total > 0:
                deflections = sum(
                    1 for c in classifications
                    if c.get("response_label") in ("DEFLECTION", "TOPIC_CHANGE", "IGNORED")
                )
                score.question_dodge_rate = round(deflections / total, 2)

                if score.question_dodge_rate > 0.30:
                    score.red_flags.append(
                        f"Question Dodge Rate = {score.question_dodge_rate:.0%} "
                        f"({deflections}/{total} questions deflected/ignored)"
                    )

                score.overall_score = round(1.0 - score.question_dodge_rate, 2)

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        data_gaps.append(f"Q&A classification parse failed: {e}")

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


def verify_moat_claims(
    transcript_text: str,
    financial_data_summary: str = "",
    data_gaps: list[str] = None,
) -> MoatVerification:
    """
    Adversarial RAG approach to moat verification.

    Force the model to identify claims and then evaluate each against evidence.
    "UNVERIFIABLE" is always preferable to a guess.
    """
    if data_gaps is None:
        data_gaps = []

    result = MoatVerification()

    combined_text = transcript_text
    if financial_data_summary:
        combined_text += f"\n\n---\n\nFinancial Data Summary:\n{financial_data_summary}"

    # FIX 2: Truncate with warning
    truncated = _truncate_with_warning(
        combined_text, MOAT_MAX_CHARS, "Moat verification", data_gaps,
    )

    # FIX 3: Safe LLM call
    response, error = _safe_llm_call(
        call_deepseek, MOAT_VERIFICATION_PROMPT, truncated,
        label="Moat verification",
    )
    if error:
        result.data_gaps.append(error)
        return result

    try:
        clean = _strip_llm_json_fences(response)
        parsed = json.loads(clean)

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


# ── Qualitative Analysis Prompts ─────────────────────────────────────────────

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


# ── FIX 1: Concurrent Gemini Execution ───────────────────────────────────────
#
# The four qualitative extraction calls (business model, quarterly updates,
# management commentary, risks) are independent — no data dependency between
# them. Running them sequentially wastes 20-40 seconds.
#
# We use ThreadPoolExecutor (not asyncio) because:
# (a) call_gemini is synchronous
# (b) This function is itself called from asyncio.to_thread by the orchestrator,
#     so it's already off the event loop
# (c) ThreadPoolExecutor.map handles the join cleanly

def _run_gemini_extraction(
    prompt_key: str,
    transcript_text: str,
    rag_context: str,
    data_gaps: list[str],
) -> tuple[str, str]:
    """
    Run a single Gemini extraction task. Returns (prompt_key, result_text).
    FIX 3: Wraps call in _safe_llm_call for crash safety.
    """
    prompt = PROMPTS[prompt_key]
    response, error = _safe_llm_call(
        call_gemini, prompt, transcript_text,
        label=f"Gemini extraction ({prompt_key})",
        extra_context=rag_context if rag_context else None,
    )

    if error:
        data_gaps.append(error)
        return prompt_key, ""

    return prompt_key, deduplicate_markdown(response)


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
    1-4. Qualitative extraction via Gemini (concurrent — FIX 1)
    5.   Management evasion scoring (DeepSeek — Q&A classification only)
    6.   Adversarial moat verification (DeepSeek — structured reasoning)

    If rag_context is provided, it is passed as extra_context to all Gemini calls.
    """
    result = NLPAnalysisResult(ticker=ticker)

    # ── Steps 1-4: Concurrent Gemini extraction (FIX 1) ──────────────
    gemini_tasks = [
        "business_model",
        "key_quarterly_updates",
        "management_commentary",
        "risks_uncertainties",
    ]

    # Thread-safe list for data_gaps from concurrent tasks
    gemini_errors: list[str] = []

    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="gemini") as pool:
        futures = {
            pool.submit(
                _run_gemini_extraction,
                task_key, transcript_text, rag_context, gemini_errors,
            ): task_key
            for task_key in gemini_tasks
        }

        results_map = {}
        for future in as_completed(futures):
            task_key = futures[future]
            try:
                key, text = future.result()
                results_map[key] = text
            except Exception as e:
                # FIX 3: Even if future.result() raises, we don't crash
                gemini_errors.append(
                    f"Gemini extraction ({task_key}): Unexpected error — {e}"
                )
                results_map[task_key] = ""

    # Assign results
    result.business_model_summary = results_map.get("business_model", "")
    result.quarterly_updates = results_map.get("key_quarterly_updates", "")
    result.management_commentary = results_map.get("management_commentary", "")
    result.risks = results_map.get("risks_uncertainties", "")

    # Surface any Gemini errors
    result.data_gaps.extend(gemini_errors)

    # ── Step 5: Management evasion scoring (Q&A sections only!) ──────
    if qa_sections:
        qa_combined = "\n\n---\n\n".join(qa_sections)
        result.management_evasion = score_management_evasion(
            qa_combined, result.data_gaps,
        )
    else:
        result.data_gaps.append(
            "No Q&A sections available — management evasion scoring skipped."
        )

    # ── Step 6: Adversarial moat verification ────────────────────────
    result.moat_verification = verify_moat_claims(
        transcript_text, financial_data_summary, result.data_gaps,
    )

    return result

    