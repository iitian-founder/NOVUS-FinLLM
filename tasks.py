# tasks.py — Novus FinLLM Multi-Agent Pipeline
"""
Restructured background task pipeline using the 5-agent MAS architecture.

Agent Flow:
  EXTRACTION → FETCH FINANCIALS → TRIAGE → FORENSIC QUANT ║ NLP ANALYST → PM SYNTHESIS

Law 1: GROUND EVERYTHING
Law 2: SEPARATE CALCULATION FROM NARRATION
Law 3: MAKE UNCERTAINTY EXPLICIT
"""

import json
import time
import asyncio
from rq import get_current_job

from cio_orchestrator import run_orchestrator
from agents.extraction import run_extraction_pipeline
from rag_engine import ingest_documents, get_collection_stats, get_context_for_agent


PROGRESS_STAGES = [
    "extract_pdfs",
    "ingest_rag",
    "fetch_financials",
    "triage",
    "forensic_analysis",
    "nlp_analysis",
    "assumptions",
    "projections",
    "pm_synthesis",
    "assemble",
]


def _update_progress(stage: str, extra: dict | None = None):
    job = get_current_job()
    if not job:
        return
    job.meta['stage'] = stage
    if 'stages' not in job.meta:
        job.meta['stages'] = PROGRESS_STAGES
    if extra:
        job.meta.update(extra)
    job.save_meta()


def generate_financial_report_from_rag(ticker):
    """
    RAG-Only Mode: Full Novus analysis using ONLY:
      1. Stored documents in ChromaDB (previously ingested)
      2. Screener.in financial data (auto-fetched)

    No PDF upload needed — everything comes from the vector store.
    """
    try:
        from rag_engine import query as rag_query, get_collection_stats, get_context_for_agent

        # ═══════════════════════════════════════════════════════════════
        # CHECK RAG STORE
        # ═══════════════════════════════════════════════════════════════
        _update_progress('ingest_rag')
        stats = get_collection_stats(ticker)
        if stats['total_chunks'] == 0:
            raise ValueError(
                f"No documents found for ticker {ticker} in RAG store. "
                f"Please ingest documents first via /ingest_local."
            )
        print(f"[RAG-Only] Found {stats['total_chunks']} chunks for {ticker}")

        # ═══════════════════════════════════════════════════════════════
        # BUILD SYNTHETIC TRANSCRIPT FROM RAG STORE
        # Pull the most relevant chunks to create a "transcript"
        # ═══════════════════════════════════════════════════════════════
        _update_progress('extract_pdfs')
        print("[RAG-Only] Building synthetic transcript from stored documents...")

        key_queries = [
            "company overview business model revenue segments",
            "financial performance revenue profit growth",
            "management guidance outlook strategy",
            "risks challenges headwinds concerns",
            "competitive advantage moat market position",
            "quarterly results recent performance",
            "capital allocation dividends buyback capex",
            "industry trends market opportunity",
        ]

        transcript_parts = []
        seen_ids = set()
        for q in key_queries:
            results = rag_query(ticker, q, top_k=5)
            for r in results:
                chunk_hash = hash(r['text'][:100])
                if chunk_hash not in seen_ids:
                    seen_ids.add(chunk_hash)
                    meta = r.get('metadata', {})
                    transcript_parts.append(
                        f"[Source: {meta.get('filename', '?')} | {meta.get('doc_type', '?')}]\n"
                        f"{r['text']}"
                    )

        combined_text = "\n\n---\n\n".join(transcript_parts)
        print(f"[RAG-Only] Built transcript: {len(combined_text)} chars from {len(transcript_parts)} chunks")

        if not combined_text:
            raise ValueError("Could not build transcript from RAG store — documents may be empty.")

        # ═══════════════════════════════════════════════════════════════
        # STATE-MACHINE ORCHESTRATION
        # ═══════════════════════════════════════════════════════════════
        def progress_cb(stage, active, completed, **kwargs):
            extra = {
                "active_agents": active,
                "completed_agents": completed
            }
            # Forward per-agent streaming outputs if provided
            if "agent_outputs" in kwargs:
                extra["agent_outputs"] = kwargs["agent_outputs"]
            _update_progress(stage, extra)

        user_query = f"Analyze {ticker} focusing on forensics, competitive moat, narrative shifts, and capital allocation."
        
        print(f"[Pipeline] Starting State-Machine Orchestrator for {ticker}")
        state = asyncio.run(run_orchestrator(
            ticker=ticker,
            user_query=user_query,
            context_data=combined_text,
            progress_callback=progress_cb
        ))

        # ═══════════════════════════════════════════════════════════════
        # ASSEMBLE FINAL REPORT
        # ═══════════════════════════════════════════════════════════════
        _update_progress('assemble')
        print("[Pipeline] Assembling final Novus report...")

        # Write the final report into job metadata so the frontend
        # can render it immediately during the next poll cycle.
        _update_progress('assemble', {
            "final_report": state.final_report,
            "active_agents": [],
            "completed_agents": ["planning", "fsa_quant", "forensic_investigator", "narrative_decoder", "moat_architect", "capital_allocator", "synthesis"]
        })

        return {
            "final_report": state.final_report,
            "status": "completed"
        }

    except Exception as e:
        _update_progress('failed', {"error": str(e)})
        raise


def generate_financial_report(ticker, files_data):
    """
    Background task: Full Novus FinLLM Multi-Agent Report Generation.

    Pipeline:
      1. EXTRACTION PIPELINE — PDF parsing, Q&A isolation
      2. FETCH FINANCIALS — Screener.in scraping (existing proven logic)
      3. TRIAGE AGENT — Kill screen on fetched data (deterministic)
      4. FORENSIC QUANT — Pure math
      5. NLP ANALYST — Structured LLM analysis
      6. ASSUMPTIONS & PROJECTIONS — Financial modeling
      7. PM SYNTHESIS — Investment thesis
      8. ASSEMBLE — Final report
    """
    try:
        # ═══════════════════════════════════════════════════════════════
        # AGENT 2: EXTRACTION PIPELINE (runs first — needs PDFs)
        # ═══════════════════════════════════════════════════════════════
        _update_progress('extract_pdfs')
        print(f"[Agent 2: Extraction] Processing PDFs...")

        extraction_result = run_extraction_pipeline(ticker, files_data)
        combined_text = extraction_result.raw_text

        if not combined_text:
            raise ValueError("Could not extract text from the provided PDF files.")

        # ═══════════════════════════════════════════════════════════════
        # RAG INGESTION — Parse, chunk, embed, store all documents
        # ═══════════════════════════════════════════════════════════════
        _update_progress('ingest_rag')
        print("[RAG Engine] Ingesting documents into vector store...")

        try:
            # Build (filename, bytes) pairs for RAG ingestion
            rag_files = [(f"doc_{i+1}.pdf", fb) for i, fb in enumerate(files_data)]
            rag_stats = ingest_documents(ticker, rag_files)
            print(f"[RAG Engine] ✅ Ingested {rag_stats['total_chunks']} chunks, "
                  f"types={rag_stats['doc_types']}")
        except Exception as e:
            print(f"[RAG Engine] ⚠️ RAG ingestion failed (non-fatal): {e}")
            rag_stats = {"total_chunks": 0, "doc_types": [], "error": str(e)}

        # ═══════════════════════════════════════════════════════════════
        # STATE-MACHINE ORCHESTRATION
        # ═══════════════════════════════════════════════════════════════
        def progress_cb(stage, active, completed, **kwargs):
            extra = {
                "active_agents": active,
                "completed_agents": completed
            }
            if "agent_outputs" in kwargs:
                extra["agent_outputs"] = kwargs["agent_outputs"]
            _update_progress(stage, extra)

        user_query = f"Analyze {ticker} focusing on forensics, competitive moat, narrative shifts, and capital allocation."
        
        print(f"[Pipeline] Starting State-Machine Orchestrator for {ticker}")
        state = asyncio.run(run_orchestrator(
            ticker=ticker,
            user_query=user_query,
            context_data=combined_text,
            progress_callback=progress_cb
        ))

        # ═══════════════════════════════════════════════════════════════
        # ASSEMBLE FINAL REPORT
        # ═══════════════════════════════════════════════════════════════
        _update_progress('assemble')
        print("[Pipeline] Assembling final Novus report...")

        # Write the final report into job metadata so the frontend
        # can render it immediately during the next poll cycle.
        # Rebuild agent_outputs for the final payload
        from cio_orchestrator import format_dict_as_markdown
        agent_outputs = {}
        for name, finding in state.specialist_findings.items():
            if finding.structured_output:
                md_lines = format_dict_as_markdown(finding.structured_output, indent=0)
                agent_outputs[name] = "\n".join(md_lines)
            else:
                agent_outputs[name] = finding.raw_output[:1500] if finding.raw_output else "[processing...]"

        _update_progress('assemble', {
            "final_report": state.final_report,
            "agent_outputs": agent_outputs,
            "active_agents": [],
            "completed_agents": ["planning", "fsa_quant", "forensic_investigator", "narrative_decoder", "moat_architect", "capital_allocator", "synthesis"]
        })

        report_data = {
            "final_report": state.final_report,
            "agent_outputs": agent_outputs,
            "rag_stats": rag_stats,
            "status": "completed",
        }

        print(f"[Pipeline] ✅ Report generation complete for {ticker}")
        return report_data

    except Exception as e:
        _update_progress('failed', {"error": str(e)})
        raise