# logic.py — Backward-compatibility shim
"""
This file previously contained 1,400+ lines of mixed concerns.
It has been decomposed into focused modules:

  - llm_clients.py          → call_deepseek(), call_gemini(), client, deepseek_model_name
  - prompts.py              → PROMPTS dict
  - scrapers/screener_html.py → get_yearly_financial_statements_html(), extract_financial_data_from_html()
  - projections/engine.py   → calculate_financial_projections(), estimate_future_pe(), etc.
  - utils/pdf.py            → extract_text_from_pdfs_from_bytes()
  - utils/formatters.py     → compact_financial_data_for_llm()

All symbols are re-exported here for backward compatibility.
New code should import from the specific module directly.
"""

# LLM clients
from llm_clients import (
    client,
    deepseek_model_name,
    gemini_client,
    call_deepseek,
    call_gemini,
)

# (Legacy screener and projections modules removed entirely)


