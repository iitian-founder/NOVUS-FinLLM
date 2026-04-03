"""
═══════════════════════════════════════════════════════════════════════════════
NOVUS v3 MIGRATION GUIDE
═══════════════════════════════════════════════════════════════════════════════

WHAT CHANGED AND WHY — FILE BY FILE

Project Structure:
    novus_v3/
    ├── core/
    │   ├── llm_client.py        ← Replaces: llm_clients.py (adds tool calling)
    │   ├── tools.py             ← NEW: shared tool registry + 8 financial tools
    │   ├── react_engine.py      ← NEW: multi-turn reasoning loop + verification
    │   ├── prompt_composer.py   ← NEW: dynamic sector-aware prompt assembly
    │   └── agent_base_v3.py     ← Replaces: agent_base.py (ReAct + audit trail)
    ├── agents/
    │   └── all_agents.py        ← Replaces: 6 separate agent files
    └── orchestrator/
        └── cio_v3.py            ← Replaces: cio_orchestrator.py


═══════════════════════════════════════════════════════════════════════════════
PER-AGENT COMPARISON: v2 vs v3
═══════════════════════════════════════════════════════════════════════════════

┌─────────────────────┬──────────────────────────┬──────────────────────────────┐
│ Agent               │ v2 (current)             │ v3 (new)                     │
├─────────────────────┼──────────────────────────┼──────────────────────────────┤
│ forensic_quant      │ ✅ Pure Python (Grade A)  │ Same architecture + Piotroski│
│                     │ No changes needed        │ F-score, Altman Z-score      │
├─────────────────────┼──────────────────────────┼──────────────────────────────┤
│ forensic_investigator│ ❌ Raw schema in prompt  │ ReAct loop + document search │
│                     │ No input validation      │ + compute_ratio tool         │
│                     │ Local Citation model     │ + cross_reference tool       │
│                     │ 1 LLM call               │ + self-verification pass     │
│                     │                          │ + sector-specific red flags  │
│                     │                          │ 4-6 LLM calls, 15K tokens   │
├─────────────────────┼──────────────────────────┼──────────────────────────────┤
│ narrative_decoder   │ ❌ Raw schema in prompt  │ ReAct loop + guidance search │
│                     │ Assumes Q3+Q4 both exist │ + hedging language detector  │
│                     │ LLM computes scores      │ Scores computed in Python    │
│                     │ 1 LLM call               │ 3-5 LLM calls, 12K tokens   │
├─────────────────────┼──────────────────────────┼──────────────────────────────┤
│ moat_architect      │ ✅ Example-based (Grade B)│ Same quality + tool use      │
│                     │ Hardcoded ticker→sector  │ + competitive data search    │
│                     │                          │ Sector passed by orchestrator│
├─────────────────────┼──────────────────────────┼──────────────────────────────┤
│ capital_allocator   │ ✅ Example-based (Grade B)│ Same quality + tool use      │
│                     │                          │ + capital decision search    │
│                     │                          │ + goodwill ratio via tool    │
├─────────────────────┼──────────────────────────┼──────────────────────────────┤
│ management_quality  │ ❌ DOES NOT EXIST        │ NEW: governance, promoter    │
│                     │                          │ pledge, KMP stability, board │
│                     │                          │ independence, compensation   │
├─────────────────────┼──────────────────────────┼──────────────────────────────┤
│ pm_synthesis        │ ⚠️ Hardcoded state keys  │ Dynamic: reads ALL agents    │
│                     │ Bypasses AgentBase       │ Proper ReAct with tools      │
│                     │                          │ Conflict data injected       │
├─────────────────────┼──────────────────────────┼──────────────────────────────┤
│ extraction          │ ⚠️ Vision commented out  │ NOT CHANGED (separate infra) │
│                     │                          │ Recommend: Gemini Vision +   │
│                     │                          │ page.get_pixmap() rendering  │
├─────────────────────┼──────────────────────────┼──────────────────────────────┤
│ CIO orchestrator    │ ⚠️ LLM-generated plan    │ Deterministic phase plan     │
│                     │ O(n²) conflict check     │ Python conflict detection    │
│                     │ Only 1 reflection path   │ 3 reflection triggers        │
│                     │                          │ Dynamic agent output routing │
└─────────────────────┴──────────────────────────┴──────────────────────────────┘


═══════════════════════════════════════════════════════════════════════════════
TOKEN & COST COMPARISON
═══════════════════════════════════════════════════════════════════════════════

v2 (per agent):
    Input:  ~50K tokens (full document dumped)
    Output: ~2K tokens (JSON)
    Calls:  1 (+ up to 2 retries)
    Total:  ~52K tokens × 1 call = 52K tokens

v3 (per agent):
    Call 1: ~2K input (prompt + overview) → 500 output (think + tool call)
    Call 2: ~3K input (+ tool result)     → 500 output (think + tool call)
    Call 3: ~4K input (+ tool result)     → 500 output (think + tool call)
    Call 4: ~5K input (+ tool result)     → 2K output (final JSON)
    Verify: ~4K input (findings)          → 1K output (verification)
    Total:  ~18K input + ~4.5K output = ~22.5K tokens across 5 calls

RESULT: v3 uses ~57% FEWER total tokens but makes 5x more calls.
The calls are focused (model reads 2-3K of targeted context per turn)
instead of one massive 50K context window where attention is diluted.


═══════════════════════════════════════════════════════════════════════════════
HOW TO IMPLEMENT INCREMENTALLY
═══════════════════════════════════════════════════════════════════════════════

You don't have to rewrite everything at once. Here's the migration path:

WEEK 1: Core infrastructure
    - Deploy llm_client.py (backward compatible — call_simple works like old API)
    - Deploy tools.py (shared tool library)
    - Deploy react_engine.py (ReAct loop)
    - TEST: Run react_loop with a simple prompt + search_document tool

WEEK 2: First agent migration — forensic_investigator
    - This is your worst agent (Grade D), so highest ROI to upgrade first
    - Deploy the v3 ForensicInvestigatorV3
    - Run SIDE-BY-SIDE with v2 on 10 companies
    - Compare: does v3 find red flags that v2 misses?
    - Measure: token usage, latency, accuracy

WEEK 3: narrative_decoder migration
    - Second worst agent (Grade D)
    - Deploy NarrativeDecoderV3 with guidance search + hedging detector
    - Side-by-side testing

WEEK 4: New agent — management_quality
    - No v2 equivalent, so no migration — pure addition
    - Deploy ManagementQualityV3
    - Test on known governance failures (retrospective: Satyam, DHFL, Yes Bank)

WEEK 5: Orchestrator migration
    - Deploy cio_v3.py
    - Swap out old orchestrator
    - Test full pipeline end-to-end

WEEK 6: prompt_composer + sector modules
    - Deploy dynamic prompt composition
    - Build sector modules for your top 3 sectors
    - Test sector-awareness (same company analyzed as wrong sector vs right sector)


═══════════════════════════════════════════════════════════════════════════════
WHAT STAYS THE SAME
═══════════════════════════════════════════════════════════════════════════════

1. forensic_quant — Your best agent. Pure Python. No LLM calls.
   v3 keeps the same architecture. Only additions: Piotroski F-score,
   Altman Z-score. The "Python calculates, LLM narrates" law is preserved.

2. extraction.py — Document ingestion pipeline. Not part of this refactor.
   Recommend upgrading separately (Gemini Vision with page rendering).

3. DeepSeek as the LLM backend — v3 works with the same DeepSeek API.
   The llm_client.py is OpenAI-compatible, so it also works with any
   provider (OpenAI, Anthropic, local Llama) if you ever want to switch.

4. novus_state.py — v3 has its own AuditTrail dataclass but the
   existing NovusState can coexist during migration. The orchestrator
   outputs an OrchestratorState that replaces NovusState when ready.


═══════════════════════════════════════════════════════════════════════════════
FUTURE ADDITIONS (NOT IN THIS RELEASE)
═══════════════════════════════════════════════════════════════════════════════

1. Peer Comparison Agent (Python-only)
   - Fetch data for 4-5 peers from Screener.in
   - Compute relative valuation, relative margins, relative growth
   - Critical for institutional credibility

2. Live Data Feed Agent
   - BSE bulk/block deal monitor
   - Mutual fund holding changes (AMFI data)
   - FII/DII flow tracking
   - Insider trading disclosures (SAST filings)

3. ESG & Regulatory Agent
   - SEBI orders and penalties
   - RBI circulars (for banks)
   - NPPA price controls (for pharma)
   - Environmental compliance

4. Position Monitor / Alert Engine
   - Persist thesis and kill criteria
   - Watch for trigger events
   - Push alerts when thesis breaks

5. Evaluation Framework
   - Ground-truth datasets per agent
   - Automated accuracy benchmarking
   - Analyst feedback collection loop
"""
