"""
CIO Orchestrator — State-Machine Router for Novus FinLLM

Architecture:
1. AgentRegistry: Dynamic dispatch — no hardcoded if/else.
2. NovusState Blackboard: All agents share a single Pydantic state object.
3. Reflection Loop: Forensic red flags auto-retrigger FSA_Quant verification.
4. Circuit Breaker: 3 failures → [FAILED: REQUIRES_HUMAN_AUDIT].
5. Telegraphic Synthesis: Merge all findings into a single Novus Report.
6. FIX 2: Structured Data Routing — Quant agents receive clean API data,
   NLP agents receive raw text context.
"""

import os
import json
import asyncio
from typing import Dict, List, Type, Callable

from logic import call_deepseek
from novus_state import (
    NovusState, UserContext, AuditPlan, AuditTask,
    AgentFinding, DiscrepancyEntry, TaskStatus,
)
from agents.agent_base import AgentBase
from agents.fsa_quant import FSAQuantAgent
from agents.forensic_investigator import ForensicInvestigatorAgent
from agents.narrative_decoder import NarrativeDecoderAgent
from agents.moat_architect import MoatArchitectAgent
from agents.capital_allocator import CapitalAllocatorAgent
from structured_data_fetcher import get_structured_data_fetcher, StructuredDataFetcher


# ── Agent Registry ────────────────────────────────────────────────────────────

class AgentRegistry:
    """Dynamic registry mapping agent names to AgentBase instances."""

    def __init__(self):
        self._agents: Dict[str, AgentBase] = {}

    def register(self, agent: AgentBase):
        self._agents[agent.agent_name] = agent

    def get(self, name: str) -> AgentBase | None:
        # Exact match first
        if name in self._agents:
            return self._agents[name]
        # Fuzzy match for planner flexibility
        name_lower = name.lower()
        for key, agent in self._agents.items():
            if key in name_lower or name_lower in key:
                return agent
        return None

    def list_agents(self) -> List[str]:
        return list(self._agents.keys())

    def __contains__(self, name: str) -> bool:
        return self.get(name) is not None


# ── Build the Default Registry ────────────────────────────────────────────────

def build_default_registry() -> AgentRegistry:
    registry = AgentRegistry()
    registry.register(FSAQuantAgent())
    registry.register(ForensicInvestigatorAgent())
    registry.register(NarrativeDecoderAgent())
    registry.register(MoatArchitectAgent())
    registry.register(CapitalAllocatorAgent())
    return registry


REGISTRY = build_default_registry()


# ── Phase 1: Strategic Audit Plan ─────────────────────────────────────────────

async def generate_strategic_audit_plan(
    ticker: str, user_query: str, registry: AgentRegistry,
    progress_callback: Callable = None
) -> AuditPlan:
    """Use DeepSeek R1 to decompose the query into vertical tasks."""
    if progress_callback:
        progress_callback("planning", ["planning"], [])
    
    print(f"> [CIO] Generating Strategic Audit Plan for {ticker}")

    available = ", ".join(registry.list_agents())
    prompt = (
        "You are the Lead 'Planner' AI for the Novus FinLLM platform. "
        "Decompose the user query into a 'Strategic Audit Plan' with 3-5 tasks. "
        f"Available specialist agents: [{available}]. "
        "Each task must have a 'description' and an 'assignee' from the agent list. "
        "Respond ONLY in valid JSON: "
        '{"tasks": [{"description": "...", "assignee": "agent_name"}]}'
    )

    response_text = await asyncio.to_thread(call_deepseek, prompt, user_query)

    try:
        clean = response_text.strip()
        if '```json' in clean:
            clean = clean.split('```json', 1)[1].rsplit('```', 1)[0]
        elif '```' in clean:
            clean = clean.split('```', 1)[1].rsplit('```', 1)[0]

        parsed = json.loads(clean.strip())
        tasks = [
            AuditTask(description=t["description"], assignee=t["assignee"])
            for t in parsed.get("tasks", [])
        ]
        return AuditPlan(tasks=tasks)

    except Exception as e:
        print(f"> [CIO] Plan parse error: {e}. Using fallback plan.")
        return AuditPlan(tasks=[
            AuditTask(description="Financial statement analysis", assignee="fsa_quant"),
            AuditTask(description="Forensic accounting scan", assignee="forensic_investigator"),
            AuditTask(description="Narrative and guidance analysis", assignee="narrative_decoder"),
        ])


# ── Phase 2: Parallel Execution ──────────────────────────────────────────────

async def execute_agent(
    agent: AgentBase, ticker: str, context_data: str, state: NovusState,
    structured_context: str = None
) -> AgentFinding:
    """Execute a single agent in a thread (agents are sync internally).
    
    FIX 2: If structured_context is provided (for quant agents), it is
    prepended to the raw context_data so the agent receives clean
    tabular financial data alongside the original text.
    """
    if structured_context:
        enriched_context = (
            structured_context + 
            "\n\n=== RAW DOCUMENT CONTEXT ===\n" +
            context_data
        )
    else:
        enriched_context = context_data
    return await asyncio.to_thread(agent.execute, ticker, enriched_context, state)


async def run_parallel_execution(
    state: NovusState, context_data: str, registry: AgentRegistry,
    progress_callback: Callable = None
):
    """Dispatch all planned agents in parallel with live streaming.
    
    FIX 2: Data Routing Architecture:
      - QUANT agents (fsa_quant, capital_allocator) receive structured
        Screener.in JSON tables + raw text context.
      - NLP agents (narrative_decoder, moat_architect, forensic_investigator)
        receive ONLY raw text context from PDFs/RAG.
    
    Each agent's output is pushed to the progress_callback immediately
    upon completion so the frontend can render results incrementally.
    """
    print(f"> [CIO] Parallel Execution — {len(state.audit_plan.tasks)} tasks")

    # ── FIX 2: Fetch structured data for quant agents ────────────────
    fetcher = get_structured_data_fetcher()
    structured_context = None
    try:
        structured_context = await asyncio.to_thread(
            fetcher.format_as_context, state.user_context.ticker
        )
        if structured_context and "NO STRUCTURED DATA" not in structured_context:
            print(
                f"> [CIO] ✅ Structured data fetched for {state.user_context.ticker} "
                f"({len(structured_context)} chars)"
            )
        else:
            print(f"> [CIO] ⚠️ No structured data available — quant agents will use text only")
            structured_context = None
    except Exception as e:
        print(f"> [CIO] ⚠️ Structured data fetch failed (non-fatal): {e}")
        structured_context = None

    valid_tasks = []
    active_agent_names = []
    completed_agent_names = ["planning"]

    for task in state.audit_plan.tasks:
        agent = registry.get(task.assignee)
        if agent is None:
            print(f"> [CIO] WARNING: No agent found for '{task.assignee}', skipping.")
            task.status = TaskStatus.FAILED
            task.error_message = f"Agent '{task.assignee}' not found in registry"
            continue
        if state.circuit_breaker.is_tripped(agent.agent_name):
            print(f"> [CIO] Circuit breaker tripped for '{agent.agent_name}', skipping.")
            task.status = TaskStatus.REQUIRES_HUMAN_AUDIT
            continue
        task.status = TaskStatus.RUNNING
        active_agent_names.append(task.assignee)
        valid_tasks.append((agent, task))

    if progress_callback:
        progress_callback("parallel_execution", list(active_agent_names), list(completed_agent_names))

    # ── FIX 2: Route data based on agent type ────────────────────────
    async def _run_and_tag(agent, task_obj):
        """Wrapper that tags the result with agent info and routes data."""
        try:
            # Quant agents receive structured API data; NLP agents get raw text only
            agent_structured = None
            if StructuredDataFetcher.should_receive_structured_data(agent.agent_name):
                agent_structured = structured_context
                print(f"> [CIO] 📊 Routing structured data → {agent.agent_name}")
            else:
                print(f"> [CIO] 📄 Routing raw text only → {agent.agent_name}")

            result = await execute_agent(
                agent, state.user_context.ticker, context_data, state,
                structured_context=agent_structured
            )
            return agent, task_obj, result, None
        except Exception as exc:
            return agent, task_obj, None, exc

    pending = [_run_and_tag(agent, task_obj) for agent, task_obj in valid_tasks]

    for coro in asyncio.as_completed(pending):
        agent, task_obj, result, error = await coro

        if error:
            print(f"> [CIO] Agent {agent.agent_name} CRASHED: {error}")
            task_obj.status = TaskStatus.FAILED
            task_obj.error_message = str(error)
            state.specialist_findings[agent.agent_name] = AgentFinding(
                agent_name=agent.agent_name,
                raw_output=f"[EXECUTION CRASHED] {error}",
                confidence=0.0,
            )
        else:
            task_obj.status = TaskStatus.DONE
            state.specialist_findings[agent.agent_name] = result
            print(f"> [CIO] ✅ Agent {agent.agent_name} COMPLETED (conf: {result.confidence})")

        # Update progress immediately — stream this agent's output
        if agent.agent_name in active_agent_names:
            active_agent_names.remove(agent.agent_name)
        completed_agent_names.append(agent.agent_name)

        if progress_callback:
            # Build partial agent_outputs dict for the frontend
            agent_outputs = {}
            for name, finding in state.specialist_findings.items():
                if finding.structured_output:
                    md_lines = format_dict_as_markdown(finding.structured_output, indent=0)
                    agent_outputs[name] = "\n".join(md_lines)
                else:
                    agent_outputs[name] = finding.raw_output[:1500] if finding.raw_output else "[processing...]"
            
            progress_callback(
                "parallel_execution",
                list(active_agent_names),
                list(completed_agent_names),
                agent_outputs=agent_outputs
            )


# ── Phase 3: Reflection Loop ─────────────────────────────────────────────────

async def run_reflection_loop(
    state: NovusState, context_data: str, registry: AgentRegistry,
    progress_callback: Callable = None
):
    """
    If forensic_investigator flags HIGH severity issues,
    automatically re-trigger fsa_quant for metric verification.
    """
    if not state.has_high_severity_forensic_flags():
        print("> [CIO] Reflection Loop: No high-severity forensic flags. Skipping.")
        return

    print("> [CIO] ⚠ REFLECTION TRIGGERED: Forensic flags HIGH severity → re-triggering FSA_Quant")
    state.reflection_triggers.append("forensic_investigator → fsa_quant")

    if progress_callback:
        progress_callback("reflection", ["fsa_quant"], ["planning", "forensic_investigator", "narrative_decoder", "moat_architect", "capital_allocator"])

    fsa_agent = registry.get("fsa_quant")
    if fsa_agent and not state.circuit_breaker.is_tripped("fsa_quant"):
        # Build focused context with forensic flags
        forensic_data = state.specialist_findings.get("forensic_investigator")
        enhanced_context = context_data
        if forensic_data and forensic_data.structured_output:
            enhanced_context += (
                "\n\n--- FORENSIC FLAGS FOR VERIFICATION ---\n"
                + json.dumps(forensic_data.structured_output, indent=2)
            )

        result = await execute_agent(fsa_agent, state.user_context.ticker, enhanced_context, state)
        state.specialist_findings["fsa_quant_reflection"] = result
        print("> [CIO] Reflection FSA_Quant complete.")


# ── Phase 4: Conflict Check ──────────────────────────────────────────────────

async def perform_conflict_check(state: NovusState) -> List[DiscrepancyEntry]:
    """Cross-reference agent findings for critical discrepancies."""
    print("> [CIO] Cross-referencing findings for Tension Detection")

    combined = ""
    for name, finding in state.specialist_findings.items():
        snippet = finding.raw_output[:800] if finding.raw_output else "[no output]"
        combined += f"\n--- {name.upper()} (confidence: {finding.confidence}) ---\n{snippet}\n"

    prompt = (
        "You are the CIO performing a 'Conflict Check' across agent findings. "
        "Check if any agent's claims contradict another's metrics. "
        "Output JSON array of discrepancies: "
        '[{"source_agent": "...", "target_agent": "...", "severity": "LOW|MEDIUM|HIGH|CRITICAL", "description": "..."}] '
        "If no discrepancies, output: []"
    )

    response = await asyncio.to_thread(call_deepseek, prompt, combined)

    try:
        clean = response.strip()
        if '```json' in clean:
            clean = clean.split('```json', 1)[1].rsplit('```', 1)[0]
        elif '```' in clean:
            clean = clean.split('```', 1)[1].rsplit('```', 1)[0]
        parsed = json.loads(clean.strip())
        return [DiscrepancyEntry(**d) for d in parsed if isinstance(d, dict)]
    except Exception:
        return []


# ── Phase 5: Telegraphic Synthesis ────────────────────────────────────────────

def format_dict_as_markdown(data, indent=0) -> List[str]:
    """Recursively formats a dictionary or list into a Markdown list."""
    lines = []
    pad = "  " * indent
    if isinstance(data, dict):
        for k, v in data.items():
            key_str = str(k).replace('_', ' ').title()
            if isinstance(v, (dict, list)) and v:
                lines.append(f"{pad}- **{key_str}**:")
                lines.extend(format_dict_as_markdown(v, indent + 1))
            elif isinstance(v, (dict, list)) and not v:
                lines.append(f"{pad}- **{key_str}**: None")
            else:
                lines.append(f"{pad}- **{key_str}**: {v}")
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, (dict, list)) and item:
                lines.append(f"{pad}- 🔹")
                lines.extend(format_dict_as_markdown(item, indent + 1))
            else:
                lines.append(f"{pad}- {item}")
    else:
        lines.append(f"{pad}- {data}")
    return lines

async def generate_final_report(state: NovusState) -> str:
    """Merge all agent sub-reports and synthesize an institutional-grade CIO report using DeepSeek."""
    print("> [CIO] Generating Institutional Initiation Report...")
    
    # 1. Compile the raw facts / findings with agent labels
    facts = []
    facts.append(f"Ticker: {state.user_context.ticker}")
    facts.append(f"Query: {state.user_context.query}")
    
    if state.discrepancies:
        facts.append("\n[DISCREPANCIES DETECTED]")
        for d in state.discrepancies:
            facts.append(f"- {d.severity}: {d.source_agent} vs {d.target_agent} -> {d.description}")

    # Compile confidence scores for threshold checks
    facts.append("\n[AGENT CONFIDENCE SCORES]")
    for name, finding in state.specialist_findings.items():
        facts.append(f"  {name.upper()}: {finding.confidence}")

    facts.append("\n[AGENT FINDINGS]")
    for name, finding in state.specialist_findings.items():
        snippet = finding.raw_output if finding.raw_output else "[no output]"
        facts.append(f"--- {name.upper()} (confidence: {finding.confidence}) ---\n{snippet}\n")

    compiled_facts = "\n".join(facts)

    # 2. Build the strict institutional CIO synthesis prompt
    import datetime
    current_date = datetime.datetime.now().strftime('%B %d, %Y')
    
    prompt = f"""You are the Chief Investment Officer (CIO) Synthesis Agent for Novus, an institutional buy-side forensic equity research platform. 

Your job is to ingest raw outputs from parallel specialized sub-agents (Fundamental, Forensic, Valuation, and Narrative) and synthesize them into a ruthless, institutional-grade Buy-Side Initiation Report.

You are writing for Mutual Fund Portfolio Managers. Your tone must be aggressively objective, skeptical, and focused purely on cash realities, variant perception, and risk. Do not use marketing fluff. 

### STRICT CONSTRAINTS:
1. NO HALLUCINATIONS: You may only use the data provided in the sub-agent inputs below. If a sub-agent failed to provide data for a specific section, you MUST write "DATA UNAVAILABLE - REQUIRES MANUAL REVIEW". Do not attempt to guess or calculate missing metrics.
2. CONFIDENCE THRESHOLDS: If any sub-agent reports a confidence score below 0.60, you must add a [DATA WARNING] tag next to that specific metric.
3. FORMATTING: You must strictly adhere to the Markdown structure below. Do not skip or rearrange sections.
4. DATE & AUTHORSHIP: Use EXACTLY the following — Date: {current_date} | Prepared by: Novus MAS. Do NOT hallucinate any other date or author.

### REQUIRED OUTPUT STRUCTURE:

# NOVUS INSTITUTIONAL INITIATION REPORT: {state.user_context.ticker}
*Generated by Novus MAS | Date: {current_date}*

## SECTION 1: The Fundamental Baseline
**Business Overview:**
* [Bullet 1: Core business model and primary revenue driver]
* [Bullet 2: Target market and distribution scale]
* [Bullet 3: Recent macroeconomic tailwinds/headwinds]

**Segmental Scorecard:**
* [Extract and format the top 3 segments, their revenue, and EBIT margins from inputs. Compare YoY if available.]

**The Competitive Moat:**
* [Synthesize the MOAT_ARCHITECT input. Focus on barriers to entry, pricing power, and market share.]

## SECTION 2: The Novus Forensic Audit
**Earnings Quality & Cash Realities:**
* [Synthesize the FSA_QUANT input. Explicitly state the Cash Conversion Cycle, EBITDA-to-OCF ratio, and flag any divergence between reported PAT and Operating Cash Flow.]

**The Narrative Decoder:**
* [Synthesize the NARRATIVE_DECODER input. Highlight how management's tone has shifted over the last 2-4 quarters. Note any specific metrics they have stopped mentioning.]

**Capital Allocation & Red Flags:**
* [Synthesize the FORENSIC_INVESTIGATOR and CAPITAL_ALLOCATOR inputs. Flag any Related Party Transactions, Capital Work in Progress (CWIP) bloat, or questionable M&A.]

## SECTION 3: Divergence & Valuation Context
**Consensus Divergence:**
* [Highlight where the FSA_QUANT math explicitly contradicts consensus sell-side estimates or management guidance.]

**Scenario Matrix:**
* [Insert Base, Bull, and Bear case revenue and EBITDA margin projections provided by the VALUATION_AGENT. State the core assumption driving each.]

## SECTION 4: CIO Investment Verdict
**Forensic Risk Score:** [Low / Moderate / High / Critical]

**Investment Thesis:**
* [Provide a 3-sentence synthesis of the risk-reward tradeoff based ONLY on the data above.]

**Pre-Call Ammunition (Questions for Management):**
* [Generate 3 highly specific, uncomfortable questions for the human analyst to ask the CFO on the next earnings call, based directly on the forensic anomalies and narrative shifts identified above.]

---
NOW SYNTHESIZE THE FOLLOWING SUB-AGENT OUTPUTS INTO THE ABOVE STRUCTURE:"""
    
    synthesis = await asyncio.to_thread(call_deepseek, prompt, compiled_facts)
    
    # 3. Build the complete report: Synthesis first, then raw audit trail
    lines = []
    lines.append(synthesis)
    lines.append("")
    lines.append("---")
    lines.append("")

    # Audit Plan Summary
    lines.append("## [ STRATEGIC AUDIT PLAN ]")
    for t in state.audit_plan.tasks:
        status_icon = {"done": "✅", "failed": "❌", "requires_human_audit": "🔴"}.get(t.status, "⏳")
        lines.append(f"  {status_icon} {t.description} → [{t.assignee}] ({t.status})")
    lines.append("")

    # Discrepancies
    if state.discrepancies:
        lines.append("## [ DISCREPANCY ALERTS ]")
        for d in state.discrepancies:
            lines.append(f"  [{d.severity}] {d.source_agent} ↔ {d.target_agent}: {d.description}")
        lines.append("")

    # Agent Findings (raw audit trail)
    lines.append("## [ SPECIALIST FINDINGS — RAW AUDIT TRAIL ]")
    for name, finding in state.specialist_findings.items():
        lines.append(f"\n### {name.upper()}")
        confidence_tag = f" [DATA WARNING]" if finding.confidence < 0.60 else ""
        lines.append(f"  Confidence: {finding.confidence}{confidence_tag}")
        lines.append(f"  Execution: {finding.execution_time_s}s")
        lines.append(f"  Citations verified: {sum(1 for c in finding.citations if c.verified)}/{len(finding.citations)}")

        if finding.data_gaps:
            lines.append(f"  ⚠️ Data Gaps: {finding.data_gaps}")

        lines.append("\n  **Output**:")
        if finding.structured_output:
            formatted = format_dict_as_markdown(finding.structured_output, indent=1)
            lines.extend(formatted)
        else:
            snippet = finding.raw_output[:2000] if finding.raw_output else "[no output]"
            lines.append(f"\n{snippet}")
    lines.append("")

    # Circuit Breaker State
    tripped = [k for k, v in state.circuit_breaker.failure_counts.items() if v >= state.circuit_breaker.max_failures]
    if tripped:
        lines.append("## [ CIRCUIT BREAKER ]")
        for agent in tripped:
            lines.append(f"  🔴 {agent}: [FAILED: REQUIRES_HUMAN_AUDIT]")
        lines.append("")

    return "\n".join(lines)


# ── Core Execution Engine ─────────────────────────────────────────────────────

async def run_orchestrator(
    ticker: str,
    user_query: str,
    context_data: str,
    fiscal_year: str = "FY24",
    registry: AgentRegistry = None,
    progress_callback: Callable = None,
) -> NovusState:
    """Main Orchestration Loop — State Machine."""

    if registry is None:
        registry = REGISTRY

    # Initialize shared blackboard state
    state = NovusState(
        user_context=UserContext(ticker=ticker, query=user_query, fiscal_year=fiscal_year)
    )

    # Phase 1: Planning
    state.audit_plan = await generate_strategic_audit_plan(ticker, user_query, registry, progress_callback)

    # Phase 2: Parallel Execution
    await run_parallel_execution(state, context_data, registry, progress_callback)

    # Phase 3: Reflection Loop
    await run_reflection_loop(state, context_data, registry, progress_callback)

    # Phase 4: Conflict Check
    if progress_callback:
        progress_callback("conflict_check", ["synthesis"], ["planning", "fsa_quant", "forensic_investigator", "narrative_decoder", "moat_architect", "capital_allocator"])
    state.discrepancies = await perform_conflict_check(state)

    # Phase 5: Synthesis
    if progress_callback:
        progress_callback("synthesis", ["synthesis"], ["planning", "fsa_quant", "forensic_investigator", "narrative_decoder", "moat_architect", "capital_allocator"])
    state.final_report = await generate_final_report(state)

    if progress_callback:
        progress_callback("synthesis", [], ["planning", "fsa_quant", "forensic_investigator", "narrative_decoder", "moat_architect", "capital_allocator", "synthesis"])

    print("> [CIO] Orchestration Complete.")
    return state


# ── CLI Test Runner ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    async def _test():
        ticker = "HINDUNILVR"
        query = "Analyze HINDUNILVR FY24 with forensic and capital allocation focus"
        context = (
            "Revenue: 63,121 Cr. EBITDA: 16,198 Cr. PAT: 10,671 Cr. "
            "Total Assets: 32,000 Cr. Equity: 8,500 Cr. OCF: 12,500 Cr. "
            "CWIP has been at 1,200 Cr for 3 years. Related party royalty increased 18% YoY. "
            "Auditor noted Emphasis of Matter regarding subsidiary guarantees. "
            "Management guided 8-10% volume growth in Q3 but Q4 delivered 3%. "
        )

        print(f"\n{'='*60}")
        print(f"NOVUS CIO ORCHESTRATOR — TEST RUN")
        print(f"Registry: {REGISTRY.list_agents()}")
        print(f"{'='*60}\n")

        state = await run_orchestrator(ticker, query, context)
        print("\n\n" + state.final_report)

    asyncio.run(_test())
