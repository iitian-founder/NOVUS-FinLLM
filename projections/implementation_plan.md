# Modular Financial Projections Agent Architecture (Final Revision)

This revised plan incorporates a critical architectural shift: **Universal Tooling and Agent Reuse**. Rather than locking tools (Prowess API, Web/News search, Math) and capabilities inside the `projections/` directory, we will lift them to the root level so all agents in the repository (e.g., CIO orchestrator, critic agent) can access them. We will also directly integrate the existing `narrative_decoder.py` agent for management guidance rather than reproducing its logic.

> **Note on Tooling:** We will use [AlphaVantage](https://www.alphavantage.co/) for the News API and financial data gathering.

## Proposed Universal Tooling Structure (Root Level)

We will create a centralized `tools/` directory at the root of the project to house universal tools usable by *any* LangChain/LangGraph agent.

```text
giga-finanalytix/
├── tools/                    # Universal Tools (NEW)
│   ├── __init__.py
│   ├── financial_tools.py    # Wraps provess_client logic into standard @tool functions
│   ├── search_tools.py       # Web Search and News API tools (AlphaVantage)
│   ├── rag_tools.py          # Clean wrapper around root rag_engine.py for agent-tool use
│   └── math_tools.py         # Financial formula mathematical calculations
├── agents/                   # (Existing)
│   └── narrative_decoder.py  # (Existing) Evaluates management guidance
├── provess_client/           # (Existing)
└── rag_engine.py             # (Existing)
```

## Projections Graph Structure

The actual LangGraph specifically for orchestrating projections will remain in the `projections/` directory, pulling in the universal tools and the narrative decoder.

```text
projections/
├── __init__.py               # Exposes public API: `def run_projections(company_name, years=3): ...`
├── state.py                  # Defines AgentState schema, supporting Map-Reduce parallel state
├── graph.py                  # Main workflow construction and entry point
├── tools_registry.py         # Imports and binds the universal tools for the projections graph
├── utils.py                  # Local materiality rules (>5% segments) and prompts
├── nodes/                    # LangGraph Node Implementations
│   ├── __init__.py
│   ├── orchestrator.py       # Decomposes revenue/expenses
│   ├── segment_researcher.py # Parallel spoke node (News/Web per segment)
│   ├── expense_analyzer.py   # Parallel spoke node (News/Web per material expense)
│   ├── synthesizer.py        # Compresses segment projections to numbers using math_tools
│   └── blender.py            # Invokes `narrative_decoder.py` and blends 70/30 with bottom-up projection
└── edges/                    # Graph routing logic
    ├── __init__.py
    └── routers.py            # LangGraph `Send` API mapping for parallel spoke branches
```

## The Workflow & Component Interactions

1. **Orchestrator**: Queries RAG (via universal RAG tool). Lists segments > 5% and expenses > 20% using local deterministic utility functions.
2. **Parallel Spokes (`segment_researcher`, `expense_analyzer`)**: The `Send` API spins up parallel branches. Each uses the universal Web and News API tools (AlphaVantage) to research specific factors.
3. **Synthesis**: The `synthesizer` node utilizes `tools/math_tools.py` to compress the research into concrete numerical bottom-up projections.
4. **Management Narrative (`blender.py`)**: Before finalizing, the blender node calls the existing `agents/narrative_decoder.py` pipeline. It gets the guidance analysis and weights it with the synthesized bottom-up numbers.

## Verification Plan & Toy Graph

1. **Step 1: Toy Graph (`projections/test_send_api.py`)**
   I will build a minimal script that proves we can spin up 3 fake `segment_researcher` nodes in parallel using LangGraph `Send` and reduce their state dictionaries flawlessly. 

2. **Step 2: Scaffolding the Architecture**
   Once the toy graph proves the Map-Reduce state logic is working locally, I will build out the `tools/` root directory and fill out the `projections/` node/edge directory tree with the boilerplate implementations.
