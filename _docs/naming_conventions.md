# Novus FinLLM Naming Conventions

To ensure consistency and maintainability across the Novus FinLLM platform, all contributors must adhere to the following naming standards:

## 1. Agent Identifiers (`agent_name`)
All agent names must be **lowercase snake_case**, representing their functional roles.
- **Correct:** `forensic_quant`, `moat_architect`, `capital_allocator`
- **Incorrect:** `FSA_Quant`, `fsa_quant`, `NLP_Analyst`

## 2. Findings & Outputs (`AgentFinding`)
When referencing the structured or raw outputs of an agent, standardize on **`finding`** or **`agent_finding`** (for single objects) and **`specialist_findings`** (for the global state mapping).
- **Correct:** `finding`, `agent_finding`, `specialist_findings`
- **Incorrect:** `a_outs`, `agent_outputs`, `findings_dict`

## 3. Contextual Data (`context_data`)
The aggregate string of text and RAG chunks passed to the LLM should be standardized.
- **Correct:** `context_data`
- **Incorrect:** `enriched_context`, `challenge_context`, `combined_text`

## 4. Execution State (`completed_agents`)
When tracking which agents have finished their work in the orchestration loop, use **`completed_agents`**.
- **Correct:** `completed_agents`
- **Incorrect:** `completed_agent_names`, `seen_completions`, `all_done`

## 5. Endpoints & API
All endpoints must live under the blueprint `/api/v1/`.
- **Correct:** `/api/v1/generate_report`, `/api/v1/research/initiate`
- **Incorrect:** `/generate_report`, `/api/screener_data`
