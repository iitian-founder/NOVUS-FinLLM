"""
structured_data_fetcher.py — Structured API Data Router for Novus MAS

FIX 2: Bypasses unstructured PDF OCR for quant agents by routing clean,
structured financial data from Screener.in directly to quant agents
(forensic_quant, capital_allocator) while NLP agents continue receiving raw text.

Architecture:
  PDF Text → narrative_decoder, moat_architect
  Screener JSON API → forensic_quant, capital_allocator, (valuation)
"""

import json
import logging
from typing import Dict, Any, Optional

from screener_scraper import fetch_screener_tables

logger = logging.getLogger(__name__)


# ── Agent Classification ─────────────────────────────────────────────────────

QUANT_AGENTS = {"fsa_quant", "forensic_quant", "capital_allocator"}
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

    @staticmethod
    def _coerce_numeric(value: Any) -> Optional[float]:
        """Best-effort conversion of scraped cell values into floats."""
        if value is None:
            return None

        if isinstance(value, (int, float)):
            return float(value)

        text = str(value).strip()
        if not text or text.lower() == "nan" or text == "-":
            return None

        cleaned = (
            text.replace(",", "")
            .replace("%", "")
            .replace("x", "")
            .replace("₹", "")
            .strip()
        )

        try:
            return float(cleaned)
        except ValueError:
            return None

    @staticmethod
    def _find_row_label(row: Dict[str, Any]) -> str:
        for key, value in row.items():
            if key.startswith("Unnamed") or key.lower() == "line item":
                return str(value).strip()

        first_value = next(iter(row.values()), "")
        return str(first_value).strip()

    @classmethod
    def _extract_latest_metric(
        cls, rows: list[Dict[str, Any]], aliases: tuple[str, ...]
    ) -> Optional[float]:
        """
        Find the latest numeric value for a row whose label loosely matches one
        of the provided aliases.
        """
        normalized_aliases = tuple(alias.lower() for alias in aliases)

        for row in rows:
            label = cls._find_row_label(row).lower()
            if not label:
                continue

            if not any(alias in label for alias in normalized_aliases):
                continue

            numeric_values: list[float] = []
            for key, value in row.items():
                key_lower = str(key).lower()
                if key_lower.startswith("unnamed") or key_lower == "line item":
                    continue

                numeric = cls._coerce_numeric(value)
                if numeric is not None:
                    numeric_values.append(numeric)

            if numeric_values:
                return numeric_values[-1]

        return None

    def fetch_raw(self, ticker: str) -> Dict[str, Any]:
        """
        Backward-compatible accessor used by planning-time assumption tuning.
        Returns the fetched tables plus a few flattened top-level metrics.
        """
        structured = self.fetch(ticker)
        ratios_rows = structured.get("tables", {}).get("Ratios", [])

        debt_equity = self._extract_latest_metric(
            ratios_rows,
            (
                "debt to equity",
                "debt/equity",
                "debt-equity",
                "debt equity",
            ),
        )

        return {
            **structured,
            "debt_equity": debt_equity,
        }

    def format_as_context(self, ticker: str) -> str:
        """
        Convert structured financial tables into canonical JSON so downstream
        agents can parse it deterministically instead of reverse-engineering a
        markdown table dump.
        """
        data = self.fetch(ticker)
        tables = data.get("tables", {})

        if not tables:
            return f"[NO STRUCTURED DATA AVAILABLE FOR {ticker}]"

        payload = {
            "ticker": data.get("ticker", ticker.upper()),
            "source": data.get("source", "screener.in"),
            "tables": tables,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

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
