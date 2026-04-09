"""
query_planner.py
================
Budget-aware retrieval planner for hybrid search.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List

from document_registry import shortlist_documents


@dataclass
class RetrievalBudget:
    max_cold_ingest_files: int = 8
    max_vector_results: int = 10
    max_lexical_results: int = 20
    timeout_seconds: int = 20


@dataclass
class QueryPlan:
    ticker: str
    strategy: str
    reason: str
    budgets: Dict
    lexical_shortlist: List[Dict]
    cold_ingest_paths: List[str]


def choose_strategy(collection_chunk_count: int, question: str) -> str:
    q = question.lower()
    if collection_chunk_count >= 200:
        return "vector_plus_lexical"
    if any(k in q for k in ("latest", "recent", "q4", "quarter", "guidance", "rating")):
        return "cold_start_then_vector"
    return "lexical_then_vector"


def plan_query(
    ticker: str,
    question: str,
    collection_chunk_count: int,
    budget: RetrievalBudget | None = None,
) -> QueryPlan:
    budget = budget or RetrievalBudget()
    shortlist = shortlist_documents(
        ticker=ticker,
        query=question,
        limit=budget.max_lexical_results,
    )
    strategy = choose_strategy(collection_chunk_count, question)
    reason = (
        "Collection is warm, combine vector and lexical evidence."
        if strategy == "vector_plus_lexical"
        else "Collection is cold or query is freshness-heavy; ingest a bounded shortlist."
    )
    cold_paths = []
    if strategy in {"cold_start_then_vector", "lexical_then_vector"} and collection_chunk_count < 80:
        cold_paths = [d["source_path"] for d in shortlist[: budget.max_cold_ingest_files]]

    return QueryPlan(
        ticker=ticker.upper(),
        strategy=strategy,
        reason=reason,
        budgets=asdict(budget),
        lexical_shortlist=shortlist,
        cold_ingest_paths=cold_paths,
    )
