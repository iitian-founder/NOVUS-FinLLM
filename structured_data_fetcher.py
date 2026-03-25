"""
structured_data_fetcher.py — Structured API Data Router for Novus MAS

FIX 2: Bypasses unstructured PDF OCR for quant agents by routing clean,
structured financial data from Screener.in directly to QUANT agents
(FSA_QUANT, CAPITAL_ALLOCATOR) while NLP agents continue receiving raw text.

Architecture:
  PDF Text → narrative_decoder, moat_architect
  Screener JSON API → fsa_quant, capital_allocator, (valuation)
"""

import json
import logging
from typing import Dict, Any, Optional

from screener_scraper import fetch_screener_tables

logger = logging.getLogger(__name__)


# ── Agent Classification ─────────────────────────────────────────────────────

QUANT_AGENTS = {"fsa_quant", "capital_allocator"}
NLP_AGENTS = {"narrative_decoder", "moat_architect", "forensic_investigator"}


class StructuredDataFetcher:
    """
    Institutional data feed abstraction layer.
    
    Currently backed by Screener.in (live scraping).
    Designed for future drop-in replacement with XBRL feeds,
    FactSet API, Capitaline, or Bloomberg B-PIPE.
    """

    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}

    def fetch(self, ticker: str) -> Dict[str, Any]:
        """
        Fetch structured financial data for a given ticker.
        Returns a dictionary with P&L, Balance Sheet, Cash Flow, and Ratios.
        Results are cached per-session to avoid redundant HTTP requests.
        """
        ticker = ticker.upper().strip()

        if ticker in self._cache:
            logger.info(f"[StructuredDataFetcher] Cache hit for {ticker}")
            return self._cache[ticker]

        logger.info(f"[StructuredDataFetcher] Fetching structured data for {ticker}")

        try:
            raw = fetch_screener_tables(ticker)
            tables = raw.get("tables", {})

            if not tables:
                logger.warning(f"[StructuredDataFetcher] No tables found for {ticker}")
                return {"ticker": ticker, "tables": {}, "error": "No structured data available"}

            structured = {
                "ticker": ticker,
                "source": raw.get("source", "screener.in"),
                "tables": tables,
            }

            self._cache[ticker] = structured
            logger.info(
                f"[StructuredDataFetcher] ✅ {ticker}: "
                f"{len(tables)} tables, "
                f"sections={list(tables.keys())}"
            )
            return structured

        except Exception as e:
            logger.error(f"[StructuredDataFetcher] Failed for {ticker}: {e}")
            return {"ticker": ticker, "tables": {}, "error": str(e)}

    def format_as_context(self, ticker: str) -> str:
        """
        Convert structured financial tables into a clean text context
        string optimized for quant agent consumption.

        Format:
          === PROFIT & LOSS (10Y) ===
          | Line Item | Mar 2020 | Mar 2021 | ... |
          | Revenue   | 38,785   | 45,311   | ... |
        """
        data = self.fetch(ticker)
        tables = data.get("tables", {})

        if not tables:
            return f"[NO STRUCTURED DATA AVAILABLE FOR {ticker}]"

        lines = [
            f"=== STRUCTURED FINANCIAL DATA: {ticker} ===",
            f"Source: {data.get('source', 'screener.in')}",
            "",
        ]

        for title, rows in tables.items():
            lines.append(f"--- {title.upper()} ---")
            if not rows:
                lines.append("  [No data]")
                continue

            # Extract column headers
            headers = list(rows[0].keys())
            # Clean "Unnamed: 0" to "Line Item"
            clean_headers = [
                "Line Item" if h.startswith("Unnamed") else h
                for h in headers
            ]
            lines.append("  | " + " | ".join(clean_headers) + " |")

            # Each row
            for row in rows:
                vals = []
                for h in headers:
                    v = row.get(h, "")
                    if v is None or str(v) == "nan":
                        v = ""
                    vals.append(str(v))
                lines.append("  | " + " | ".join(vals) + " |")

            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def should_receive_structured_data(agent_name: str) -> bool:
        """Determine if an agent should receive structured API data."""
        return agent_name in QUANT_AGENTS

    @staticmethod
    def should_receive_text_only(agent_name: str) -> bool:
        """Determine if an agent should receive only raw text context."""
        return agent_name in NLP_AGENTS


# ── Module-level singleton ───────────────────────────────────────────────────

_fetcher_instance: Optional[StructuredDataFetcher] = None


def get_structured_data_fetcher() -> StructuredDataFetcher:
    """Get or create the singleton StructuredDataFetcher instance."""
    global _fetcher_instance
    if _fetcher_instance is None:
        _fetcher_instance = StructuredDataFetcher()
    return _fetcher_instance


if __name__ == "__main__":
    fetcher = StructuredDataFetcher()
    ctx = fetcher.format_as_context("HINDUNILVR")
    print(ctx[:2000])
    print(f"\n--- Total context length: {len(ctx)} chars ---")
