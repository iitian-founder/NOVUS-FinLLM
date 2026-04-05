"""
followup_qa.py — Follow-up Q&A Sub-Loop Node
==============================================
Answers analyst follow-up questions about assumptions using
research context, historical data, and management guidance.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from langchain_core.messages import HumanMessage, SystemMessage
from projections.llm_providers import get_chat_model


async def followup_qa_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Answer the analyst's follow-up question using available research context.
    Appends the Q&A pair to qa_history and routes back to analyst_review.
    """
    question = state.get("followup_question", "")
    company = state.get("company_name", "")

    print(f"\n{'='*60}")
    print(f"💬 FOLLOW-UP Q&A: {question[:80]}")
    print(f"{'='*60}")

    if not question:
        return {"qa_history": state.get("qa_history", [])}

    # Gather context for answering
    context = {
        "assumptions": state.get("draft_assumptions", {}),
        "historical_analysis": state.get("historical_analysis", {}),
        "mgmt_guidance": state.get("mgmt_guidance", {}),
        "segment_research": state.get("segment_results", {}),
        "expense_research": state.get("expense_results", {}),
        "deviation_flags": state.get("deviation_flags", {}),
    }

    prompt = f"""The analyst working on {company}'s financial projections asked:

"{question}"

Available research context:
{json.dumps(context, indent=2, default=str)[:6000]}

Provide a clear, data-backed answer. Reference specific numbers and sources.
If the question is about a deviation from management guidance, explain why
the bottom-up assumption differs and whether the analyst should adjust it."""

    llm = get_chat_model("deepseek", temperature=0.3)
    response = await llm.ainvoke([
        SystemMessage(content="You are a senior equity research analyst. Answer questions with specific data and reasoning."),
        HumanMessage(content=prompt),
    ])

    answer = response.content.strip()
    print(f"  📝 Answer: {answer[:200]}...")

    # Append to Q&A history
    qa_history = list(state.get("qa_history", []))
    qa_history.append({"question": question, "answer": answer})

    return {
        "qa_history": qa_history,
        "followup_question": None,  # clear the question
    }
