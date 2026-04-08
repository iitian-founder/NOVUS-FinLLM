"""
document_registry.py
====================
Persistent corpus registry used by the query planner.

Stores lightweight metadata for very large document corpora:
- ticker
- source path
- doc type
- period/year
- file hash
- parse/index status
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional


DEFAULT_REGISTRY_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_REGISTRY_DB = DEFAULT_REGISTRY_DIR / "corpus_registry.db"
SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".docx"}


@dataclass
class RegistryDoc:
    doc_id: str
    ticker: str
    source_path: str
    filename: str
    extension: str
    size_bytes: int
    mtime_epoch: float
    doc_type: str
    period_label: str
    content_hash: str
    parse_status: str = "discovered"
    vector_status: str = "not_indexed"
    access_count: int = 0
    last_accessed_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect(db_path: str | Path = DEFAULT_REGISTRY_DB) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_registry(db_path: str | Path = DEFAULT_REGISTRY_DB) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                doc_id TEXT PRIMARY KEY,
                ticker TEXT NOT NULL,
                source_path TEXT NOT NULL UNIQUE,
                filename TEXT NOT NULL,
                extension TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                mtime_epoch REAL NOT NULL,
                doc_type TEXT NOT NULL,
                period_label TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                parse_status TEXT NOT NULL DEFAULT 'discovered',
                vector_status TEXT NOT NULL DEFAULT 'not_indexed',
                access_count INTEGER NOT NULL DEFAULT 0,
                last_accessed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_ticker ON documents(ticker)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_doc_type ON documents(doc_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_period ON documents(period_label)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_mtime ON documents(mtime_epoch)")


def _ticker_from_path(path: Path, root: Path) -> str:
    try:
        rel_parts = path.relative_to(root).parts
        if rel_parts:
            # convention: first folder is ticker symbol
            raw = rel_parts[0]
            cleaned = re.sub(r"[^A-Za-z0-9\-&]", "", raw).upper()
            return cleaned or "UNKNOWN"
    except Exception:
        pass
    return "UNKNOWN"


def _infer_doc_type(filename: str) -> str:
    lower = filename.lower()
    if "annual" in lower and "report" in lower:
        return "annual_report"
    if "concall" in lower or "conference" in lower or "transcript" in lower:
        return "concall_transcript"
    if "presentation" in lower or "deck" in lower:
        return "investor_presentation"
    if "rating" in lower or "rationale" in lower or "crisil" in lower or "icra" in lower:
        return "credit_report"
    if "quarter" in lower or re.search(r"\bq[1-4]\b", lower):
        return "quarterly_results"
    if "filing" in lower:
        return "filing"
    return "other"


def _infer_period_label(filename: str) -> str:
    y = re.search(r"(19|20)\d{2}", filename)
    if y:
        return y.group(0)
    q = re.search(r"(?i)\bq([1-4])\b", filename)
    if q:
        return f"Q{q.group(1)}"
    return "unknown"


def _build_doc(path: Path, root: Path) -> RegistryDoc:
    stat = path.stat()
    content_sig = f"{path.resolve()}:{stat.st_size}:{stat.st_mtime}"
    content_hash = hashlib.md5(content_sig.encode("utf-8")).hexdigest()
    doc_id = hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()
    now = _utc_now()
    return RegistryDoc(
        doc_id=doc_id,
        ticker=_ticker_from_path(path, root),
        source_path=str(path.resolve()),
        filename=path.name,
        extension=path.suffix.lower(),
        size_bytes=stat.st_size,
        mtime_epoch=stat.st_mtime,
        doc_type=_infer_doc_type(path.name),
        period_label=_infer_period_label(path.name),
        content_hash=content_hash,
        created_at=now,
        updated_at=now,
    )


def iter_documents(root_path: str | Path) -> Iterable[Path]:
    root = Path(root_path).expanduser().resolve()
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            yield path


def register_corpus(root_path: str | Path, db_path: str | Path = DEFAULT_REGISTRY_DB) -> Dict[str, int]:
    init_registry(db_path)
    root = Path(root_path).expanduser().resolve()
    added = 0
    updated = 0
    skipped = 0

    with _connect(db_path) as conn:
        for path in iter_documents(root):
            doc = _build_doc(path, root)
            existing = conn.execute(
                "SELECT content_hash FROM documents WHERE source_path = ?",
                (doc.source_path,),
            ).fetchone()
            if existing and existing["content_hash"] == doc.content_hash:
                skipped += 1
                continue

            conn.execute(
                """
                INSERT INTO documents (
                    doc_id, ticker, source_path, filename, extension, size_bytes, mtime_epoch,
                    doc_type, period_label, content_hash, parse_status, vector_status,
                    access_count, last_accessed_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_path) DO UPDATE SET
                    doc_id = excluded.doc_id,
                    ticker = excluded.ticker,
                    filename = excluded.filename,
                    extension = excluded.extension,
                    size_bytes = excluded.size_bytes,
                    mtime_epoch = excluded.mtime_epoch,
                    doc_type = excluded.doc_type,
                    period_label = excluded.period_label,
                    content_hash = excluded.content_hash,
                    parse_status = 'discovered',
                    updated_at = excluded.updated_at
                """,
                (
                    doc.doc_id,
                    doc.ticker,
                    doc.source_path,
                    doc.filename,
                    doc.extension,
                    doc.size_bytes,
                    doc.mtime_epoch,
                    doc.doc_type,
                    doc.period_label,
                    doc.content_hash,
                    doc.parse_status,
                    doc.vector_status,
                    doc.access_count,
                    doc.last_accessed_at,
                    doc.created_at,
                    doc.updated_at,
                ),
            )
            if existing:
                updated += 1
            else:
                added += 1

    return {"added": added, "updated": updated, "skipped": skipped}


def shortlist_documents(
    ticker: str,
    query: str,
    limit: int = 25,
    db_path: str | Path = DEFAULT_REGISTRY_DB,
) -> List[Dict]:
    init_registry(db_path)
    ticker = ticker.upper()
    tokens = [t.lower() for t in re.findall(r"[a-zA-Z0-9]+", query) if len(t) > 2]

    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT doc_id, ticker, source_path, filename, doc_type, period_label,
                   size_bytes, mtime_epoch, parse_status, vector_status, access_count
            FROM documents
            WHERE ticker = ?
            ORDER BY mtime_epoch DESC
            LIMIT 500
            """,
            (ticker,),
        ).fetchall()

    scored = []
    for r in rows:
        hay = f"{r['filename']} {r['doc_type']} {r['period_label']}".lower()
        lex_hits = sum(1 for t in tokens if t in hay)
        freshness_days = max(1.0, (datetime.now(timezone.utc).timestamp() - r["mtime_epoch"]) / 86400.0)
        freshness_score = 1.0 / freshness_days
        score = lex_hits * 2.0 + freshness_score
        scored.append((score, dict(r)))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:limit]]


def mark_indexed(doc_paths: List[str], db_path: str | Path = DEFAULT_REGISTRY_DB) -> None:
    if not doc_paths:
        return
    now = _utc_now()
    with _connect(db_path) as conn:
        conn.executemany(
            """
            UPDATE documents
            SET parse_status = 'parsed',
                vector_status = 'indexed',
                updated_at = ?
            WHERE source_path = ?
            """,
            [(now, str(Path(p).resolve())) for p in doc_paths],
        )


def mark_accessed(doc_ids: List[str], db_path: str | Path = DEFAULT_REGISTRY_DB) -> None:
    if not doc_ids:
        return
    now = _utc_now()
    with _connect(db_path) as conn:
        conn.executemany(
            """
            UPDATE documents
            SET access_count = access_count + 1,
                last_accessed_at = ?,
                updated_at = ?
            WHERE doc_id = ?
            """,
            [(now, now, d) for d in doc_ids],
        )


def registry_stats(db_path: str | Path = DEFAULT_REGISTRY_DB) -> Dict:
    init_registry(db_path)
    with _connect(db_path) as conn:
        total_docs = conn.execute("SELECT COUNT(*) AS c FROM documents").fetchone()["c"]
        by_ticker = conn.execute(
            "SELECT ticker, COUNT(*) as c FROM documents GROUP BY ticker ORDER BY c DESC LIMIT 20"
        ).fetchall()
        indexed_docs = conn.execute(
            "SELECT COUNT(*) AS c FROM documents WHERE vector_status = 'indexed'"
        ).fetchone()["c"]
    return {
        "total_documents": total_docs,
        "indexed_documents": indexed_docs,
        "top_tickers": [dict(r) for r in by_ticker],
    }
