"""
agents/critic_agent.py — V3 Critic Agent (Phase 4: Strict Grounding)

Role: Chief Compliance and Verification Officer.
This agent does NOT generate new analysis. It cross-references every quantitative
claim made by the qualitative agents against the structured financial tables
and RAG-verified document text.

Pipeline position: Runs AFTER reflection, BEFORE PM Synthesis.
"""

import time
import json
from core.agent_base_v3 import AuditTrail, AgentV3
from core.llm_client import LLMClient
from core.tools import build_shared_tools


class CriticAgentV3(AgentV3):
    """
    Overrides AgentV3.execute() to accept peer_findings and run a
    strict verification pass against financial_tables.
    """

    agent_name = "critic_agent"

    agent_role = (
        "You are the Chief Compliance and Verification Officer for an institutional fund. "
        "Your ONLY job is to review the quantitative claims made by the qualitative agents "
        "(Moat, Capital, Narrative, Forensic) and cross-reference them against the structured "
        "financial tables. If an agent hallucinates a metric (e.g., claims 13M stores when "
        "the text says 9M, or claims 5.9% ROIC when Invested Capital is skewed), you MUST "
        "flag and correct it. You do NOT generate new analysis — you only verify."
    )

    output_example = json.dumps({
        "corrections": [
            {
                "agent_name": "moat_architect",
                "original_claim": "Distribution reach of 13M stores",
                "verified_fact": "Distribution reach of 9M stores (per FY24 Annual Report, p.42)",
                "source_citation": "[Annual Report FY24 | Page 42]",
                "action": "CORRECTED"
            },
            {
                "agent_name": "capital_allocator",
                "original_claim": "Dividend payout 95% signals inability to invest",
                "verified_fact": "Dividend payout 95% is standard for FMCG; growth is Opex-driven",
                "source_citation": "[Sector Benchmark]",
                "action": "CORRECTED"
            },
        ],
        "unverifiable_claims": [
            {
                "agent_name": "narrative_decoder",
                "claim": "Management guided for 8% volume growth",
                "reason": "No matching text found in concall transcript or quarterly results",
                "action": "FLAGGED_AS_DATA_GAP"
            }
        ],
        "verification_status": "CLEARED WITH CORRECTIONS",
        "data_gaps": None
    }, indent=2)

    # Allow more iterations — accuracy > speed
    MAX_ITERATIONS = 8
    VERIFY = False  # The critic IS the verifier; no need to self-verify

    def execute(
        self,
        ticker: str,
        document_text: str,
        financial_tables: dict,
        sector: str = "",
        extraction_signals: dict = None,
        peer_findings: dict = None,
        llm: LLMClient = None,
        dynamic_mandate: str = "",
    ) -> AuditTrail:
        """
        Override: Accepts peer_findings (dict of agent_name -> findings)
        and cross-references every quantitative claim against financial_tables.
        """
        start = time.time()
        extraction_signals = extraction_signals or {}
        peer_findings = peer_findings or extraction_signals.get("peer_findings", {})

        if not peer_findings:
            print("> [CRITIC] ⚠️ No peer findings to verify. Passing through.")
            return AuditTrail(
                agent_name=self.agent_name,
                ticker=ticker,
                sector=sector,
                findings={"corrections": [], "verification_status": "NO_FINDINGS_TO_VERIFY"},
                data_gaps=[],
                confidence=1.0,
                execution_time_s=round(time.time() - start, 2),
                steps=[],
            )

        # ── Build the verification task prompt ──
        peer_summary = json.dumps(peer_findings, indent=2, default=str)

        task_prompt = f"""You are the Chief Compliance and Verification Officer for an institutional equity fund.

## YOUR MANDATE
Review ALL quantitative claims below from our specialist analysts. For each hard number 
(store counts, margin percentages, growth rates, ROIC, distribution reach, etc.), 
use your tools to verify it against the structured financial tables or the document text.

## PEER ANALYST FINDINGS TO VERIFY
```json
{peer_summary}
```

## VERIFICATION RULES (NON-NEGOTIABLE)
1. For every hard metric, call `get_metric` or `search_document` to find the source.
2. If the number EXACTLY matches a table value or document passage, mark as VERIFIED.
3. If the number is WRONG (e.g., agent says 13M stores but source says 9M), mark as CORRECTED with the correct value and source citation.
4. If the number CANNOT be found in any source, mark as FLAGGED_AS_DATA_GAP.
5. Do NOT invent corrections. Only correct what you can prove is wrong.
6. Focus on the MOST MATERIAL claims first: ROIC, revenue growth, distribution reach, margins, debt levels.

{f"ADDITIONAL MANDATE: {dynamic_mandate}" if dynamic_mandate else ""}

Output your findings as JSON matching the schema in your instructions."""

        # ── Build tools ──
        tools = build_shared_tools(document_text, financial_tables, ticker=ticker)
        for extra_tool in self.build_agent_tools(document_text, financial_tables, ticker=ticker):
            tools.register(extra_tool)

        # ── Compose system prompt via base class machinery ──
        from core.prompt_composer import compose_prompt
        output_instruction = (
            "When you have completed your verification, output your findings "
            "as a JSON object matching this example structure:\n\n"
            f"```json\n{self.output_example}\n```\n\n"
            "CRITICAL: Only output the JSON when you have verified all material claims. "
            "Until then, keep investigating with your tools."
        )
        system_prompt = compose_prompt(
            agent_name=self.agent_name,
            agent_role=self.agent_role,
            agent_output_instruction=output_instruction,
            sector=sector,
            extraction_signals=extraction_signals,
            ticker=ticker,
        )
        if dynamic_mandate:
            system_prompt += f"\n\n## DYNAMIC MANDATE (from Lead Analyst)\n{dynamic_mandate}"

        # ── ReAct loop ──
        from core.react_engine import react_loop, ReActResult
        react_result: ReActResult = react_loop(
            system_prompt=system_prompt,
            initial_context=task_prompt,
            tools=tools,
            max_iterations=self.MAX_ITERATIONS,
            llm=llm,
        )

        # ── Compute confidence ──
        confidence = self._compute_confidence(react_result, None)

        # ── Assemble audit trail ──
        elapsed = round(time.time() - start, 2)
        trail = AuditTrail(
            agent_name=self.agent_name,
            ticker=ticker,
            sector=sector,
            steps=[
                {
                    "action": s.action or "verification",
                    "thought": (s.thought or "")[:200],
                    "observation": (s.observation or "")[:200],
                }
                for s in react_result.reasoning_chain
            ],
            findings=react_result.final_output,
            data_gaps=(react_result.final_output or {}).get("data_gaps") or [],
            verification=None,
            verified=True,  # The critic IS the verification
            confidence=confidence,
            tools_called=react_result.tools_called,
            llm_calls=react_result.total_llm_calls,
            execution_time_s=elapsed,
        )

        corrections = (react_result.final_output or {}).get("corrections", [])
        status = (react_result.final_output or {}).get("verification_status", "UNKNOWN")
        print(f"> [CRITIC] Verification complete: {len(corrections)} corrections. Status: {status} ({elapsed}s)")

        return trail
