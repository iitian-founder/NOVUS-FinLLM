# Novus FinLLM — MAS Equity Research Platform

## Architecture

Monorepo with a Python backend (Flask + RQ workers) and a Next.js 16 frontend.

```
app.py               — Flask API server (port 5001), Blueprint at /api/v1
tasks.py             — RQ background jobs (PDF + RAG-only report pipelines)
cio_orchestrator.py  — CIO State-Machine: 5-phase MAS pipeline (plan → investigate → reflect → verify → synthesise)
worker.py            — RQ worker entry point
core/                — V3 agent engine (ReAct loop, tool registry, prompt composer, sector guardrails)
agents/              — 8 specialist agents (forensic_quant, forensic_investigator, narrative_decoder, moat_architect, capital_allocator, management_quality, pm_synthesis, critic_agent)
rag_engine.py        — ChromaDB + Gemini embeddings RAG pipeline
structured_data_fetcher.py — Screener.in scraper → normalised year-keyed dicts
projections/         — LangGraph financial projections agent (GPT-3.5 + Prowess API)
provess_client/      — Prowess CMIE data fetcher + JSON cleaner
frontend/            — Next.js 16 + React 19 + TailwindCSS 4 + Zustand + Framer Motion
```

## Commands

### Backend
```bash
# Activate venv and start full stack (Redis + Worker + Flask)
./run_dev.sh

# Or manually:
source venv/bin/activate
python3 app.py                          # Flask on :5001
python3 worker.py                       # RQ worker (financial_analysis queue)

# Install deps
pip install -r requirements.txt

# Redis (required)
brew services start redis               # macOS
docker run -p 6379:6379 redis:7-alpine  # Docker alternative
```

### Frontend
```bash
cd frontend
npm install
npm run dev          # Next.js dev server on :3000
npm run build        # Production build
npm run lint         # ESLint
```

### Tests
```bash
python -m pytest tests/                                # Unit tests
python test_rag_integration.py                         # RAG integration smoke
python test_gemini.py                                  # Gemini API connectivity
```

## Environment Variables (.env)

Required: `DEEPSEEK_API_KEY`, `GEMINI_API_KEY`
Optional: `FMP_API_KEY`, `REDIS_URL`, `NOVUS_API_KEY`, `CORS_ORIGINS`
Debug: `ENABLE_DEEPSEEK_DEBUG_LOGS=true`, `ENABLE_GEMINI_DEBUG_LOGS=true`

## LLM Routing

| Model | Constant | Use Case |
|---|---|---|
| DeepSeek V3 (`deepseek-chat`) | `DEEPSEEK_V3` | Extraction, fast structured JSON, all ReAct investigation agents |
| DeepSeek R1 (`deepseek-reasoner`) | `DEEPSEEK_R1` | PM Synthesis final thesis (no temperature param — auto-omitted) |
| Gemini Flash 1.5 | — | PDF table parsing (fallback), embeddings (`gemini-embedding-001`) |
| GPT-3.5 Turbo | — | Projections agent (LangGraph, `projections/`) |

LLM clients: `core/llm_client.py` (V3 agents), `llm_clients.py` (legacy Flask routes).
Get singleton: `get_llm_client(use_r1=True)` for R1, `get_llm_client(use_r1=False)` for V3.

## Agent System — Patterns & Constraints

### Agent Base Class (`core/agent_base_v3.py`)
All agents extend `AgentV3`. Must implement: `agent_name`, `agent_role`, `output_example`, optionally `build_agent_tools()`.

### Execution Flow
`compose_prompt()` → `build_shared_tools()` + agent tools → `react_loop()` (max 12 iters) → `run_verification()` → `AuditTrail`

### Data Routing (CRITICAL)
- **Quant agents** (`forensic_quant`, `capital_allocator`): receive structured `financial_tables` dict (year-keyed, normalised by `structured_data_fetcher.py`)
- **NLP agents** (`forensic_investigator`, `narrative_decoder`, `moat_architect`): receive raw `document_text` only
- **All agents**: get shared tools (search_document, get_metric, compute_ratio, compare_years, detect_anomaly, compute_cagr, list_available_data, get_page_content)

### Financial Tables Contract
Tables are normalised at the boundary in `structured_data_fetcher.py`:
```python
# Keys: "profit_loss", "balance_sheet", "cash_flow", "quarterly_results", "ratios"
# Structure: {"Mar 2024": {"Revenue": 15747.0, "Net Profit": 2300.0, ...}}
# NBSP and trailing '+' are stripped at ingestion. TTM columns are rejected.
```

### Prompt Composition (`core/prompt_composer.py`)
Modular system: CORE modules (always) + SECTOR modules (auto-matched) + SIGNAL modules (conditional on extraction flags). Never hardcode system prompts in agents.

### Sector Guardrails (`core/sector_archetypes.py`)
40+ Indian sector archetypes with fuzzy matching. Injected into agent frameworks by the CIO orchestrator. Always use `get_guardrails(sector, fuzzy=True)`.

## Do NOT

- Use `any` types in TypeScript frontend code
- Compute financial ratios inside LLM prompts — always use `compute_ratio` tool
- Hardcode system prompts in agent files — use `compose_prompt()`
- Bypass `structured_data_fetcher.py` normalisation — raw Screener.in data has NBSP, TTM columns, and malformed line item names
- Import from `llm_clients.py` in V3 agent code — use `core/llm_client.py` instead
- Skip `source_citation` in agent findings — every qualitative claim needs `[Source | Page/Section]`
- Store secrets in code — use `.env` and `python-dotenv`
- Modify `AuditTrail` dataclass shape without updating `build_ui_payloads()` in `tasks.py`

## API Routes (Blueprint: /api/v1)

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/generate_report` | Upload PDFs + ticker → queued report job |
| POST | `/api/v1/analyze_rag` | RAG-only analysis (no PDF upload needed) |
| GET | `/api/v1/job_status/<job_id>` | Poll job progress + results |
| POST | `/api/v1/chat` | RAG-powered Q&A with conversation history |
| GET | `/api/v1/screener_data?ticker=X` | Raw Screener.in table fetch |
| POST | `/ingest_local` | Ingest PDFs from local folder into ChromaDB |
| GET | `/rag_stats/<ticker>` | ChromaDB collection stats |
| POST | `/export_pdf` | WeasyPrint HTML→PDF generation |

## Frontend Stack

Next.js 16 (App Router) + React 19 + TypeScript 5, TailwindCSS 4, Zustand (state), Framer Motion (animations), Lucide React (icons). Path alias: `@/*` → `./src/*`. Backend proxy target: `http://localhost:5001`.

## Deployment

- Backend: Vercel (`vercel.json` routes all to `app.py`) or gunicorn + separate RQ worker
- Frontend: Vercel (Next.js native) or `npm run build && npm start`
- macOS dev: requires `DYLD_FALLBACK_LIBRARY_PATH` and `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` for WeasyPrint/fork safety (set in `run_dev.sh`)
