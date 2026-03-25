"""
agents/agent_base.py — Standardized Base Class for all Novus Vertical Specialists

Enforces:
1. Structured JSON parsing with built-in retry logic (handles R1 reasoning traces).
2. Mandatory Citation Validation (substring match against context_data).
3. Telemetric Logging (reasoning path, execution time, confidence).
4. Circuit Breaker integration via NovusState.
"""

import json
import time
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from novus_state import NovusState, AgentFinding, Citation, TaskStatus


class AgentBase(ABC):
    """Abstract base class for all Novus specialist agents."""

    MAX_RETRIES = 3
    
    # ── FIX 1: Hard Kill Switch for Quant Agents ─────────────────────────
    CONFIDENCE_THRESHOLD = 0.60
    QUANT_AGENTS = {"fsa_quant", "capital_allocator"}

    @property
    @abstractmethod
    def agent_name(self) -> str:
        """Unique agent identifier, e.g., 'fsa_quant'."""
        ...

    @property
    @abstractmethod
    def output_model(self) -> Type[BaseModel]:
        """The Pydantic model class for this agent's structured output."""
        ...

    @abstractmethod
    def build_system_prompt(self, ticker: str) -> str:
        """Build the LLM system prompt for this agent."""
        ...

    def execute(self, ticker: str, context_data: str, state: NovusState) -> AgentFinding:
        """
        Standard entry point. Handles:
        - Telemetric logging
        - LLM call with structured JSON retry
        - Citation validation
        - Circuit breaker integration
        - FIX 1: Confidence kill switch for quant agents
        """
        start_time = time.time()
        print(f"> [{self.agent_name.upper()}] Executing for {ticker}...")

        # Check circuit breaker
        if state.circuit_breaker.is_tripped(self.agent_name):
            print(f"> [{self.agent_name.upper()}] CIRCUIT BREAKER TRIPPED. Skipping.")
            return AgentFinding(
                agent_name=self.agent_name,
                raw_output="[FAILED: REQUIRES_HUMAN_AUDIT] Circuit breaker tripped after repeated failures.",
                confidence=0.0,
                execution_time_s=0.0,
            )

        # Attempt structured extraction with retry
        from logic import call_deepseek
        system_prompt = self.build_system_prompt(ticker)
        last_error = None
        parsed_output = None
        raw_response = ""

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                print(f"> [{self.agent_name.upper()}] Attempt {attempt}/{self.MAX_RETRIES}")
                raw_response = call_deepseek(system_prompt, context_data)

                # Strip reasoning traces and code fences
                json_str = self._extract_json(raw_response)
                parsed_output = self.output_model.model_validate_json(json_str)

                # Success — reset circuit breaker
                state.circuit_breaker.reset(self.agent_name)
                break

            except Exception as e:
                last_error = str(e)
                print(f"> [{self.agent_name.upper()}] Attempt {attempt} failed: {last_error}")
                if attempt == self.MAX_RETRIES:
                    tripped = state.circuit_breaker.record_failure(self.agent_name)
                    if tripped:
                        print(f"> [{self.agent_name.upper()}] CIRCUIT BREAKER NOW TRIPPED.")

        # Build citations and validate them
        citations = []
        confidence = 0.0
        structured_dict = None
        data_gaps = []

        if parsed_output is not None:
            structured_dict = parsed_output.model_dump()
            citations = self._extract_citations(structured_dict)
            citations = self._validate_citations(citations, context_data)
            verified_count = sum(1 for c in citations if c.verified)
            confidence = verified_count / max(len(citations), 1)
            confidence = round(confidence, 2)
        else:
            data_gaps.append(f"Failed to parse after {self.MAX_RETRIES} attempts: {last_error}")

        # ── FIX 1: CONFIDENCE KILL SWITCH ─────────────────────────────────
        # If this is a quant agent and confidence is below threshold,
        # nullify ALL numerical outputs to prevent bad math from leaking
        # into the CIO synthesis.
        if (
            self.agent_name in self.QUANT_AGENTS
            and confidence < self.CONFIDENCE_THRESHOLD
            and structured_dict is not None
        ):
            print(
                f"> [{self.agent_name.upper()}] ⛔ KILL SWITCH: confidence {confidence} "
                f"< {self.CONFIDENCE_THRESHOLD}. Nullifying numerical outputs."
            )
            structured_dict = self._nullify_numerical_fields(structured_dict)
            data_gaps.append(
                f"[DataQualityError] Agent {self.agent_name} confidence "
                f"({confidence}) below threshold ({self.CONFIDENCE_THRESHOLD}). "
                f"All numerical outputs nullified — REQUIRES MANUAL REVIEW."
            )

        elapsed = round(time.time() - start_time, 2)

        # Build the telemetric reasoning trace
        reasoning_trace = (
            f"Agent: {self.agent_name}\n"
            f"Ticker: {ticker}\n"
            f"Attempts: {self.MAX_RETRIES if parsed_output is None else 'success'}\n"
            f"Confidence: {confidence}\n"
            f"Citations verified: {sum(1 for c in citations if c.verified)}/{len(citations)}\n"
            f"Execution time: {elapsed}s"
        )
        print(f"> [{self.agent_name.upper()}] {reasoning_trace}")

        return AgentFinding(
            agent_name=self.agent_name,
            raw_output=raw_response[:2000],
            structured_output=structured_dict,
            data_gaps=data_gaps,
            citations=citations,
            confidence=confidence,
            reasoning_trace=reasoning_trace,
            execution_time_s=elapsed,
        )

    # ── Internal Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _nullify_numerical_fields(data: Any) -> Any:
        """Recursively walk a nested dict/list and set all int/float values to None.
        
        Used by the confidence kill switch to prevent bad math from leaking
        into downstream agents when extraction confidence is below threshold.
        """
        if isinstance(data, dict):
            return {
                k: AgentBase._nullify_numerical_fields(v) 
                for k, v in data.items()
            }
        elif isinstance(data, list):
            return [AgentBase._nullify_numerical_fields(item) for item in data]
        elif isinstance(data, (int, float)):
            return None
        return data

    @staticmethod
    def _extract_json(text: str) -> str:
        """Strip reasoning traces, <think> tags, and code fences to isolate JSON."""
        # Remove <think>...</think> blocks (DeepSeek R1 reasoning)
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)

        # Extract from code fences
        if '```json' in text:
            return text.split('```json', 1)[1].rsplit('```', 1)[0].strip()
        if '```' in text:
            return text.split('```', 1)[1].rsplit('```', 1)[0].strip()

        # Try to find raw JSON object
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            return match.group(0).strip()

        return text.strip()

    @staticmethod
    def _extract_citations(data: Any, citations: list = None) -> List[Citation]:
        """Recursively extract Citation objects from a nested dict/list structure."""
        if citations is None:
            citations = []

        if isinstance(data, dict):
            # Check if this dict itself is a citation
            if "doc" in data and "quote" in data:
                citations.append(Citation(
                    doc=data.get("doc", ""),
                    pg=data.get("pg", 0),
                    quote=data.get("quote", ""),
                ))
            # Recurse into values
            for v in data.values():
                AgentBase._extract_citations(v, citations)

        elif isinstance(data, list):
            for item in data:
                AgentBase._extract_citations(item, citations)

        return citations

    @staticmethod
    def _validate_citations(citations: List[Citation], context_data: str) -> List[Citation]:
        """Verify each citation quote exists as a substring in the context_data."""
        context_lower = context_data.lower()
        for c in citations:
            # Fuzzy match: check if a significant portion of the quote exists
            quote_lower = c.quote.lower().strip()
            if len(quote_lower) > 10 and quote_lower[:40] in context_lower:
                c.verified = True
            elif quote_lower in context_lower:
                c.verified = True
            else:
                c.verified = False
        return citations
