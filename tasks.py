
from utils.logger import get_logger
logger = get_logger(__name__)
# tasks.py — Novus FinLLM Multi-Agent Pipeline
"""
Restructured background task pipeline using the V3 MAS architecture.
"""

import json
import time
import asyncio
from rq import get_current_job

# --- Persistent Event Loop for RQ Workers ---
# Prevents macOS fork() + CoreFoundation crashes by reusing the loop footprint
_runner = asyncio.Runner()

from agents.extraction import run_extraction_pipeline
from rag_engine import ingest_documents, get_collection_stats, get_context_for_agent, query_with_planner
from prompt_books import render_prompt
from structured_data_fetcher import get_structured_data_fetcher
from cio_orchestrator import analyze, OrchestratorState


from utils.formatters import format_dict_as_markdown

def build_ui_payloads(st: OrchestratorState) -> tuple[dict, dict, dict | None]:
    """Single source of truth for UI payload construction from OrchestratorState (V3)."""
    a_outs = {}
    for name, trail in st.agent_trails.items():
        if trail.findings:
            md_lines = format_dict_as_markdown(trail.findings, indent=0)
            a_outs[name] = "\n".join(md_lines)
        elif trail.data_gaps:
            a_outs[name] = f"**Data Gaps:**\n" + "\n".join(f"- {g}" for g in trail.data_gaps)
        else:
            a_outs[name] = "[processing...]"

    kill_reasons = []
    warnings = []
    passed = True

    fi = st.agent_trails.get("forensic_investigator")
    if fi and fi.findings and isinstance(fi.findings, dict):
        fo = fi.findings
        for field in ["related_party_flags", "auditor_flags", "contingent_liabilities"]:
            for issue in fo.get(field, []):
                desc = issue.get("description", "") if isinstance(issue, dict) else str(issue)
                sev = issue.get("severity", "") if isinstance(issue, dict) else ""

                if str(sev).upper() in ("HIGH", "CRITICAL"):
                    passed = False
                    kill_reasons.append(f"{field.upper()}: {desc}")
                else:
                    warnings.append(f"{field.upper()}: {desc}")

    t_res = {"passed": passed, "kill_reasons": kill_reasons, "warnings": warnings}

    f_score = None
    fsa = st.agent_trails.get("forensic_quant")
    if fsa and fsa.findings:
        f_score = fsa.findings

    return a_outs, t_res, f_score


PROGRESS_STAGES = [
    "extract_pdfs",
    "ingest_rag",
    "fetch_financials",
    "lead_analyst_planning",
    "investigation",
    "reflection",
    "conflict_check",
    "synthesis",
    "assemble",
    "complete"
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


def generate_financial_report_from_rag(ticker, template_id=None):
    """
    RAG-Only Mode: Full Novus analysis using ONLY:
      1. Stored documents in ChromaDB (previously ingested)
      2. Screener.in financial data (auto-fetched)

    No PDF upload needed — everything comes from the vector store.
    """
    try:
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
        logger.info(f"[RAG-Only] Found {stats['total_chunks']} chunks for {ticker}")

        # ═══════════════════════════════════════════════════════════════
        # BUILD SYNTHETIC TRANSCRIPT FROM RAG STORE
        # ═══════════════════════════════════════════════════════════════
        _update_progress('extract_pdfs')
        logger.info("[RAG-Only] Building synthetic transcript from stored documents...")

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
            planned = query_with_planner(ticker=ticker, question=q, top_k=5)
            results = planned.get("results", [])
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
        logger.info(f"[RAG-Only] Built transcript: {len(combined_text)} chars from {len(transcript_parts)} chunks")

        if not combined_text:
            raise ValueError("Could not build transcript from RAG store — documents may be empty.")

        # ═══════════════════════════════════════════════════════════════
        # FETCH FINANCIAL DATA
        # ═══════════════════════════════════════════════════════════════
        _update_progress('fetch_financials')
        fetcher = get_structured_data_fetcher()
        structured_data = fetcher.fetch(ticker)
        financial_tables = structured_data.get("tables", {})

        # ═══════════════════════════════════════════════════════════════
        # V3 ORCHESTRATION
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
        if template_id:
            try:
                user_query = render_prompt(template_id, {"ticker": ticker, "question": user_query})
            except Exception as exc:
                logger.info(f"[PromptBook] Failed to render template {template_id}: {exc}")
        
        # Auto-detected sector from Screener.in (e.g., "Fast Moving Consumer Goods")
        detected_sector = structured_data.get("sector", "General")
        logger.info(f"[Pipeline] Starting V3 Orchestrator for {ticker} | Sector: {detected_sector}")
        state = _runner.run(analyze(
            ticker=ticker,
            document_text=combined_text,
            financial_tables=financial_tables,
            sector=detected_sector,
            query=user_query,
            progress_callback=progress_cb
        ))

        # ═══════════════════════════════════════════════════════════════
        # ASSEMBLE FINAL REPORT
        # ═══════════════════════════════════════════════════════════════
        _update_progress('assemble')
        logger.info("[Pipeline] Assembling final Novus report...")

        agent_outputs, triage_result, forensic_scorecard = build_ui_payloads(state)

        _update_progress('assemble', {
            "final_report": state.final_report,
            "agent_outputs": agent_outputs,
            "triage_result": triage_result,
            "forensic_scorecard": forensic_scorecard,
            "active_agents": [],
            "completed_agents": ["planning", "forensic_quant", "forensic_investigator", "narrative_decoder", "moat_architect", "capital_allocator", "management_quality", "synthesis"]
        })

        return {
            "final_report": state.final_report,
            "agent_outputs": agent_outputs,
            "triage_result": triage_result,
            "forensic_scorecard": forensic_scorecard,
            "status": "completed"
        }

    except Exception as e:
        _update_progress('failed', {"error": str(e)})
        raise


def generate_financial_report(ticker, files_data):
    """
    Background task: Full Novus FinLLM Multi-Agent Report Generation.
    """
    try:
        # ═══════════════════════════════════════════════════════════════
        # AGENT 2: EXTRACTION PIPELINE (runs first — needs PDFs)
        # ═══════════════════════════════════════════════════════════════
        _update_progress('extract_pdfs')
        logger.info(f"[Agent 2: Extraction] Processing PDFs...")

        extraction_result = run_extraction_pipeline(ticker, files_data)
        combined_text = extraction_result.raw_text

        if not combined_text:
            raise ValueError("Could not extract text from the provided PDF files. This usually happens if the PDF is a scanned image without an OCR (text) layer.")

        # ═══════════════════════════════════════════════════════════════
        # RAG INGESTION
        # ═══════════════════════════════════════════════════════════════
        _update_progress('ingest_rag')
        logger.info("[RAG Engine] Ingesting documents into vector store...")

        try:
            rag_files = [(f"doc_{i+1}.pdf", fb) for i, fb in enumerate(files_data)]
            rag_stats = ingest_documents(ticker, rag_files)
            logger.info(f"[RAG Engine] ✅ Ingested {rag_stats['total_chunks']} chunks, types={rag_stats['doc_types']}")
        except Exception as e:
            logger.info(f"[RAG Engine] ⚠️ RAG ingestion failed (non-fatal): {e}")
            rag_stats = {"total_chunks": 0, "doc_types": [], "error": str(e)}

        # ═══════════════════════════════════════════════════════════════
        # FETCH FINANCIAL DATA
        # ═══════════════════════════════════════════════════════════════
        _update_progress('fetch_financials')
        fetcher = get_structured_data_fetcher()
        structured_data = fetcher.fetch(ticker)
        financial_tables = structured_data.get("tables", {})

        # ═══════════════════════════════════════════════════════════════
        # V3 ORCHESTRATION
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
        
        logger.info(f"[Pipeline] Starting V3 Orchestrator for {ticker}")
        state = _runner.run(analyze(
            ticker=ticker,
            document_text=combined_text,
            financial_tables=financial_tables,
            sector="General / Diversified",
            query=user_query,
            progress_callback=progress_cb
        ))

        # ═══════════════════════════════════════════════════════════════
        # ASSEMBLE FINAL REPORT
        # ═══════════════════════════════════════════════════════════════
        _update_progress('assemble')
        logger.info("[Pipeline] Assembling final Novus report...")

        agent_outputs, triage_result, forensic_scorecard = build_ui_payloads(state)

        _update_progress('assemble', {
            "final_report": state.final_report,
            "agent_outputs": agent_outputs,
            "triage_result": triage_result,
            "forensic_scorecard": forensic_scorecard,
            "active_agents": [],
            "completed_agents": ["planning", "forensic_quant", "forensic_investigator", "narrative_decoder", "moat_architect", "capital_allocator", "management_quality", "synthesis"]
        })

        report_data = {
            "final_report": state.final_report,
            "agent_outputs": agent_outputs,
            "triage_result": triage_result,
            "forensic_scorecard": forensic_scorecard,
            "rag_stats": rag_stats,
            "status": "completed",
        }

        logger.info(f"[Pipeline] ✅ Report generation complete for {ticker}")
        return report_data

    except Exception as e:
        _update_progress('failed', {"error": str(e)})
        raise