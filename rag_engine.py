# rag_engine.py
"""
Novus RAG Engine — Retrieval Augmented Generation over Full Company Datasets

Supports: Annual Reports, Investor Presentations, Quarterly Results,
Credit Rating Reports, Concall Transcripts, Research Reports

Stack:
  Parser: PyMuPDF (text) + Gemini Flash (complex tables)
  Embeddings: Gemini text-embedding-004
  Vector Store: ChromaDB (local, persistent)
  Chunking: Section-aware, 1000 tokens, 200 overlap
"""

from utils.logger import get_logger
logger = get_logger(__name__)
import os
import re
import json
import hashlib
import fitz  # PyMuPDF
from typing import Optional
from dotenv import load_dotenv

import chromadb
from chromadb.config import Settings
import google.generativeai as genai

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# ── Constants ────────────────────────────────────────────────────────────────

CHROMA_PERSIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")
EMBEDDING_MODEL = "models/gemini-embedding-001"
CHUNK_SIZE = 1000       # tokens (approx 4 chars per token)
CHUNK_OVERLAP = 200     # tokens overlap between chunks
MAX_CHAR_PER_CHUNK = CHUNK_SIZE * 4   # ~4000 chars
OVERLAP_CHARS = CHUNK_OVERLAP * 4     # ~800 chars


# ── Document Type Classification ─────────────────────────────────────────────

DOC_TYPE_PATTERNS = {
    "annual_report": [
        r"(?i)annual\s*report",
        r"(?i)director'?s?\s*report",
        r"(?i)board'?s?\s*report",
        r"(?i)balance\s*sheet\s*as\s*at",
        r"(?i)notes\s*to\s*(?:the\s*)?financial\s*statements",
        r"(?i)auditor'?s?\s*report",
    ],
    "concall_transcript": [
        r"(?i)(?:con\s*call|conference\s*call|earnings\s*call)",
        r"(?i)(?:q[1-4]\s*(?:fy|20))",
        r"(?i)(?:transcript|q\s*&\s*a\s*session)",
        r"(?i)(?:management|moderator)\s*:\s*",
    ],
    "investor_presentation": [
        r"(?i)investor\s*(?:presentation|deck|update)",
        r"(?i)(?:corporate|business)\s*(?:presentation|overview)",
        r"(?i)capital\s*markets?\s*day",
    ],
    "quarterly_results": [
        r"(?i)(?:quarterly|q[1-4])\s*result",
        r"(?i)financial\s*results?\s*for\s*(?:the\s*)?(?:quarter|period)",
        r"(?i)unaudited\s*financial\s*results?",
    ],
    "credit_report": [
        r"(?i)(?:credit|rating)\s*(?:report|rationale|action)",
        r"(?i)(?:crisil|icra|care|india\s*ratings|fitch|moody)",
    ],
    "research_report": [
        r"(?i)(?:equity|stock|sector)\s*research",
        r"(?i)(?:buy|sell|hold|outperform|underperform)\s*(?:rating|target)",
        r"(?i)target\s*price",
    ],
}


def classify_document_type(text: str) -> str:
    """Classify document type based on content patterns."""
    text_sample = text[:5000]  # Check first 5000 chars
    scores = {}

    for doc_type, patterns in DOC_TYPE_PATTERNS.items():
        score = sum(1 for p in patterns if re.search(p, text_sample))
        scores[doc_type] = score

    best_type = max(scores, key=scores.get)
    return best_type if scores[best_type] > 0 else "other"


# ── Section Detection ─────────────────────────────────────────────────────────

SECTION_PATTERNS = [
    # Common annual report sections
    r"(?i)^(?:#{1,3}\s+)?(director'?s?\s*report)",
    r"(?i)^(?:#{1,3}\s+)?(management\s*discussion\s*(?:and|&)\s*analysis)",
    r"(?i)^(?:#{1,3}\s+)?(notes\s*to\s*(?:the\s*)?financial\s*statements?)",
    r"(?i)^(?:#{1,3}\s+)?(corporate\s*governance)",
    r"(?i)^(?:#{1,3}\s+)?(auditor'?s?\s*report)",
    r"(?i)^(?:#{1,3}\s+)?(risk\s*management)",
    r"(?i)^(?:#{1,3}\s+)?(related\s*party\s*transactions?)",
    r"(?i)^(?:#{1,3}\s+)?(contingent\s*liabilities?)",
    # Concall sections
    r"(?i)^(?:#{1,3}\s+)?(opening\s*(?:statement|remarks?))",
    r"(?i)^(?:#{1,3}\s+)?(question\s*(?:and|&)\s*answer|q\s*&\s*a)",
    r"(?i)^(?:#{1,3}\s+)?(closing\s*(?:statement|remarks?))",
]


def detect_sections(text: str) -> list[dict]:
    """
    Detect logical sections in a document.
    Returns list of {title, start_idx, end_idx}.
    """
    sections = []
    lines = text.split('\n')
    current_section = {"title": "Introduction", "start_idx": 0, "end_idx": 0}

    char_offset = 0
    for line in lines:
        for pattern in SECTION_PATTERNS:
            match = re.match(pattern, line.strip())
            if match:
                # Close previous section
                current_section["end_idx"] = char_offset
                if current_section["end_idx"] > current_section["start_idx"]:
                    sections.append(current_section.copy())

                # Start new section
                current_section = {
                    "title": match.group(1).strip() if match.group(1) else line.strip(),
                    "start_idx": char_offset,
                    "end_idx": 0,
                }
                break

        char_offset += len(line) + 1  # +1 for newline

    # Close last section
    current_section["end_idx"] = len(text)
    if current_section["end_idx"] > current_section["start_idx"]:
        sections.append(current_section)

    # If no sections detected, treat entire document as one section
    if not sections:
        sections = [{"title": "Full Document", "start_idx": 0, "end_idx": len(text)}]

    return sections


# ── Chunking ──────────────────────────────────────────────────────────────────

def chunk_text(
    text: str,
    chunk_size: int = MAX_CHAR_PER_CHUNK,
    overlap: int = OVERLAP_CHARS,
) -> list[str]:
    """
    Split text into chunks with overlap.
    Tries to split at sentence boundaries when possible.
    """
    if len(text) <= chunk_size:
        return [text] if text.strip() else []

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        # Try to find a sentence boundary near the end
        if end < len(text):
            # Look for sentence-ending punctuation in the last 20% of the chunk
            search_start = end - int(chunk_size * 0.2)
            search_region = text[search_start:end]

            # Find the last sentence boundary
            for sep in ['. ', '.\n', ';\n', '\n\n']:
                last_sep = search_region.rfind(sep)
                if last_sep != -1:
                    end = search_start + last_sep + len(sep)
                    break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = end - overlap

    return chunks


def chunk_document_with_sections(
    text: str,
    doc_type: str,
    ticker: str,
    filename: str,
    page_map: dict = None,
) -> list[dict]:
    """
    Chunk a document with section awareness and rich metadata.
    Each chunk gets: {text, metadata: {ticker, doc_type, section, filename, chunk_id}}
    """
    sections = detect_sections(text)
    all_chunks = []
    chunk_counter = 0

    import re
    year_match = re.search(r'(19|20)\d{2}', filename)
    doc_year = int(year_match.group()) if year_match else 2020 # fallback

    for section in sections:
        section_text = text[section["start_idx"]:section["end_idx"]]
        if not section_text.strip():
            continue

        text_chunks = chunk_text(section_text)

        for i, chunk in enumerate(text_chunks):
            chunk_counter += 1
            chunk_id = hashlib.md5(
                f"{ticker}_{filename}_{section['title']}_{i}_{chunk_counter}_{chunk[:50]}".encode()
            ).hexdigest()

            all_chunks.append({
                "id": chunk_id,
                "text": chunk,
                "metadata": {
                    "ticker": ticker.upper(),
                    "doc_type": doc_type,
                    "section": section["title"],
                    "filename": filename,
                    "year": doc_year,
                    "chunk_index": i,
                    "total_section_chunks": len(text_chunks),
                    "char_count": len(chunk),
                },
            })

    return all_chunks


# ── Embedding ─────────────────────────────────────────────────────────────────

def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings using Gemini text-embedding-004.
    Free tier: 1500 requests/min, more than enough for single-company analysis.
    """
    embeddings = []

    # Gemini API supports batch embedding (max 100 at a time)
    batch_size = 100
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        try:
            result = genai.embed_content(
                model=EMBEDDING_MODEL,
                content=batch,
                task_type="retrieval_document",
            )
            embeddings.extend(result['embedding'])
        except Exception as e:
            logger.info(f"[RAG] Embedding error for batch {i}: {e}")
            # Fallback: return zero vectors (will have low similarity)
            embeddings.extend([[0.0] * 3072] * len(batch))

    return embeddings


def embed_query(query: str) -> list[float]:
    """Embed a single query string for retrieval."""
    try:
        result = genai.embed_content(
            model=EMBEDDING_MODEL,
            content=query,
            task_type="retrieval_query",
        )
        return result['embedding']
    except Exception as e:
        logger.info(f"[RAG] Query embedding error: {e}")
        return [0.0] * 3072


# ── ChromaDB Management ──────────────────────────────────────────────────────

_chroma_client = None

def get_chroma_client() -> chromadb.ClientAPI:
    """Get or create a persistent ChromaDB client as a singleton."""
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    return _chroma_client


def get_collection(ticker: str) -> chromadb.Collection:
    """Get or create a ChromaDB collection for a specific ticker."""
    client = get_chroma_client()
    collection_name = f"novus_{ticker.upper().replace('-', '_').replace('&', '_')}"
    # Ensure collection name is valid (alphanumeric + underscore, 3-63 chars)
    collection_name = re.sub(r'[^a-zA-Z0-9_]', '_', collection_name)[:63]
    if len(collection_name) < 3:
        collection_name = f"novus_{collection_name}_docs"

    return client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )


# ── Core API ──────────────────────────────────────────────────────────────────

def ingest_documents(
    ticker: str,
    files_data: list[tuple[str, bytes]],  # [(filename, bytes), ...]
    progress_callback=None,
) -> dict:
    """
    Parse, chunk, embed, and store documents in ChromaDB.
    
    Returns: {total_chunks, doc_types, sections_found}
    """
    collection = get_collection(ticker)
    total_chunks = 0
    doc_types_found = set()
    all_sections = set()

    for idx, (filename, file_bytes) in enumerate(files_data):
        if progress_callback:
            progress_callback(f"Processing {filename} ({idx+1}/{len(files_data)})")

        # Extract text from PDF
        try:
            pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
            text = ""
            for page in pdf_doc:
                text += page.get_text()
        except Exception as e:
            logger.info(f"[RAG] Failed to parse {filename}: {e}")
            continue

        if not text.strip():
            logger.info(f"[RAG] No text extracted from {filename}")
            continue

        # Classify document type
        doc_type = classify_document_type(text)
        doc_types_found.add(doc_type)

        # Chunk with section awareness
        chunks = chunk_document_with_sections(
            text, doc_type, ticker, filename
        )

        if not chunks:
            continue

        # Filter out empty/whitespace-only chunks
        chunks = [c for c in chunks if c["text"].strip()]
        if not chunks:
            continue

        # Track sections
        for c in chunks:
            all_sections.add(c["metadata"]["section"])

        # Generate embeddings
        texts = [c["text"] for c in chunks]
        embeddings = embed_texts(texts)

        # Store in ChromaDB
        collection.upsert(
            ids=[c["id"] for c in chunks],
            embeddings=embeddings,
            documents=texts,
            metadatas=[c["metadata"] for c in chunks],
        )

        total_chunks += len(chunks)
        logger.info(f"[RAG] Ingested {filename}: {len(chunks)} chunks, type={doc_type}")

    return {
        "total_chunks": total_chunks,
        "doc_types": list(doc_types_found),
        "sections_found": list(all_sections),
        "collection_name": collection.name,
    }


def query(
    ticker: str,
    question: str,
    top_k: int = 5,
    doc_type_filter: str = None,
    section_filter: str = None,
    min_year: int = None,
) -> list[dict]:
    """
    Query the RAG store for relevant chunks.
    
    Returns list of {text, metadata, distance} sorted by relevance.
    """
    collection = get_collection(ticker)

    # Build metadata filter
    where_filter = {}
    if doc_type_filter:
        where_filter["doc_type"] = doc_type_filter
    if section_filter:
        where_filter["section"] = section_filter

    if min_year:
        where_clause = {"$and": [{"ticker": ticker.upper()}, {"year": {"$gte": min_year}}]}
        for k, v in where_filter.items():
            where_clause["$and"].append({k: v})
        final_where = where_clause
    else:
        where_filter["ticker"] = ticker.upper()
        final_where = where_filter

    # Embed query
    query_embedding = embed_query(question)

    try:
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, collection.count() or 1),
            where=final_where,
        )
    except Exception as e:
        logger.info(f"[RAG] Query failed with filter {final_where}: {e}")
        # Retry without complex filters (fallback to just ticker)
        try:
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k, collection.count() or 1),
                where={"ticker": ticker.upper()}
            )
        except Exception:
            return []

    # Format results
    formatted = []
    if results and results.get("documents"):
        docs = results["documents"][0]
        metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(docs)
        dists = results["distances"][0] if results.get("distances") else [0.0] * len(docs)

        for doc, meta, dist in zip(docs, metas, dists):
            formatted.append({
                "text": doc,
                "metadata": meta,
                "relevance": round(1 - dist, 3),  # Convert distance to similarity
            })

    return formatted


def get_context_for_agent(
    ticker: str,
    agent_name: str,
    transcript_text: str = "",
) -> str:
    """
    Pre-built RAG queries tailored for each agent.
    Returns a combined context string from retrieved chunks.
    """
    collection = get_collection(ticker)

    # Check if we have any documents ingested
    if collection.count() == 0:
        return ""  # No RAG context available

    agent_queries = {
        "triage": [
            "promoter pledge shares holding percentage",
            "auditor change appointment resignation",
            "related party transactions revenue percentage",
            "equity dilution allotment shares",
        ],
        "forensic_quant": [
            "contingent liabilities off balance sheet guarantees",
            "capital expenditure capex investment plans",
            "working capital receivables payables inventory",
            "debt repayment schedule maturity profile",
        ],
        "nlp_analyst": [
            "competitive advantage moat market position",
            "management guidance outlook vision strategy",
            "industry headwinds tailwinds market size growth",
            "customer concentration revenue dependency",
        ],
        "pm_synthesis": [
            "key risks uncertainties concerns",
            "growth drivers opportunity pipeline order book",
            "capital allocation dividend buyback returns",
            "management track record execution capability",
        ],
    }

    queries = agent_queries.get(agent_name, ["company overview business model"])

    all_chunks = []
    seen_ids = set()

    for q in queries:
        results = query(ticker, q, top_k=3)
        for r in results:
            chunk_id = hashlib.md5(r["text"][:100].encode()).hexdigest()
            if chunk_id not in seen_ids:
                seen_ids.add(chunk_id)
                all_chunks.append(r)

    if not all_chunks:
        return ""

    # Build context string with source citations
    context_parts = []
    context_parts.append("--- RAG CONTEXT (from uploaded company documents) ---\n")

    for i, chunk in enumerate(all_chunks[:12], 1):  # Max 12 chunks
        meta = chunk.get("metadata", {})
        source = f"[Source: {meta.get('filename', '?')} | {meta.get('doc_type', '?')} | Section: {meta.get('section', '?')}]"
        context_parts.append(f"**Chunk {i}** {source}")
        context_parts.append(chunk["text"][:1500])  # Cap individual chunk size
        context_parts.append("")

    context_parts.append("--- END RAG CONTEXT ---\n")
    return "\n".join(context_parts)


def get_collection_stats(ticker: str) -> dict:
    """Get stats about the stored documents for a ticker."""
    collection = get_collection(ticker)
    count = collection.count()

    if count == 0:
        return {"total_chunks": 0, "doc_types": [], "sections": []}

    # Sample metadata to get doc types and sections
    sample = collection.peek(limit=min(count, 100))
    doc_types = set()
    sections = set()
    filenames = set()

    for meta in (sample.get("metadatas") or []):
        doc_types.add(meta.get("doc_type", "unknown"))
        sections.add(meta.get("section", "unknown"))
        filenames.add(meta.get("filename", "unknown"))

    return {
        "total_chunks": count,
        "doc_types": list(doc_types),
        "sections": list(sections),
        "filenames": list(filenames),
    }


def clear_collection(ticker: str) -> bool:
    """Delete all stored documents for a ticker."""
    try:
        client = get_chroma_client()
        collection_name = f"novus_{ticker.upper().replace('-', '_').replace('&', '_')}"
        collection_name = re.sub(r'[^a-zA-Z0-9_]', '_', collection_name)[:63]
        client.delete_collection(collection_name)
        return True
    except Exception:
        return False
