
"""Batch downloader for Nifty 50 concall transcripts."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

import transcripts

LOGGER = logging.getLogger(__name__)


NIFTY_50_TICKERS: tuple[str, ...] = (
    "ADANIENT",
    "ADANIPORTS",
    "APOLLOHOSP",
    "ASIANPAINT",
    "AXISBANK",
    "BAJAJ-AUTO",
    "BAJFINANCE",
    "BAJAJFINSV",
    "BEL",
    "BHARTIARTL",
    "CIPLA",
    "COALINDIA",
    "DRREDDY",
    "EICHERMOT",
    "ETERNAL",
    "GRASIM",
    "HCLTECH",
    "HDFCBANK",
    "HDFCLIFE",
    "HINDALCO",
    "HINDUNILVR",
    "ICICIBANK",
    "INDIGO",
    "INFY",
    "ITC",
    "JIOFIN",
    "JSWSTEEL",
    "KOTAKBANK",
    "LT",
    "M&M",
    "MARUTI",
    "MAXHEALTH",
    "NESTLEIND",
    "NTPC",
    "ONGC",
    "POWERGRID",
    "RELIANCE",
    "SBILIFE",
    "SBIN",
    "SHRIRAMFIN",
    "SUNPHARMA",
    "TATACONSUM",
    "TATAMOTORS",
    "TATASTEEL",
    "TCS",
    "TECHM",
    "TITAN",
    "TRENT",
    "ULTRACEMCO",
    "WIPRO",
)


def _ensure_nifty_root() -> Path:
    target_root = transcripts.DOWNLOAD_ROOT / "nifty 50"
    target_root.mkdir(parents=True, exist_ok=True)
    return target_root


def _fetch_within_directory(companies: Iterable[str], root_directory: Path) -> None:
    for symbol in companies:
        try:
            LOGGER.info("Fetching Screener transcripts for %s", symbol)
            screener_saved, screener_missing = transcripts.fetch_concall_transcripts_from_screener(
                symbol,
                root_directory=root_directory,
            )
            LOGGER.info(
                "Screener fetch complete for %s: saved=%d missing=%s",
                symbol,
                screener_saved,
                ", ".join(screener_missing) if screener_missing else "none",
            )
        except Exception as exc:
            LOGGER.exception("Failed to fetch Screener transcripts for %s: %s", symbol, exc)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    base_directory = _ensure_nifty_root()
    _fetch_within_directory(NIFTY_50_TICKERS, base_directory)
    LOGGER.info("Completed fetching Nifty 50 transcripts into %s", base_directory)


if __name__ == "__main__":
    main()
