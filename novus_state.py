"""
novus_state.py — Shared 'Blackboard' State for Novus CIO Orchestrator

Central Pydantic model tracking the full lifecycle of a multi-agent analysis run.
All agents read from and write to this state object.
"""

from typing import Dict, List, Optional
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    REQUIRES_HUMAN_AUDIT = "requires_human_audit"


class UserContext(BaseModel):
    ticker: str
    query: str
    fiscal_year: str = Field(default="FY24", description="Indian fiscal year (April-March)")
    request_time: datetime = Field(default_factory=datetime.utcnow)


class AuditTask(BaseModel):
    description: str
    assignee: str
    status: TaskStatus = TaskStatus.PENDING
    error_message: Optional[str] = None


class AuditPlan(BaseModel):
    tasks: List[AuditTask] = Field(default_factory=list)


class Citation(BaseModel):
    doc: str = Field(description="Source document filename")
    pg: int = Field(default=0, description="Page number (0 if unknown)")
    quote: str = Field(description="Exact quote from the document")
    verified: bool = Field(default=False, description="True if quote was found in context")


class AgentFinding(BaseModel):
    agent_name: str
    raw_output: str = Field(default="", description="Raw LLM response")
    structured_output: Optional[Dict] = Field(default=None, description="Parsed JSON findings")
    data_gaps: List[str] = Field(default_factory=list)
    citations: List[Citation] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Extraction confidence 0-1")
    reasoning_trace: str = Field(default="", description="Agent's logged reasoning path")
    execution_time_s: float = Field(default=0.0)


class DiscrepancyEntry(BaseModel):
    source_agent: str
    target_agent: str
    severity: str = Field(description="LOW, MEDIUM, HIGH, CRITICAL")
    description: str
    resolution: Optional[str] = None


class CircuitBreakerState(BaseModel):
    failure_counts: Dict[str, int] = Field(default_factory=dict)
    max_failures: int = Field(default=3)

    def record_failure(self, agent_name: str) -> bool:
        """Record a failure. Returns True if circuit is now tripped (>= max)."""
        self.failure_counts[agent_name] = self.failure_counts.get(agent_name, 0) + 1
        return self.failure_counts[agent_name] >= self.max_failures

    def is_tripped(self, agent_name: str) -> bool:
        return self.failure_counts.get(agent_name, 0) >= self.max_failures

    def reset(self, agent_name: str):
        self.failure_counts[agent_name] = 0


class NovusState(BaseModel):
    """The shared Blackboard state for a single orchestration run."""
    user_context: UserContext
    audit_plan: AuditPlan = Field(default_factory=AuditPlan)
    specialist_findings: Dict[str, AgentFinding] = Field(default_factory=dict)
    discrepancies: List[DiscrepancyEntry] = Field(default_factory=list)
    circuit_breaker: CircuitBreakerState = Field(default_factory=CircuitBreakerState)
    reflection_triggers: List[str] = Field(
        default_factory=list,
        description="Agents queued for re-execution by the Reflection Loop"
    )
    final_report: Optional[str] = None

    def update_task_status(self, assignee: str, status: TaskStatus, error: str = None):
        for task in self.audit_plan.tasks:
            if task.assignee == assignee:
                task.status = status
                if error:
                    task.error_message = error
                break

    def get_agent_finding(self, agent_name: str) -> Optional[AgentFinding]:
        return self.specialist_findings.get(agent_name)

    def has_high_severity_forensic_flags(self) -> bool:
        forensic = self.specialist_findings.get("forensic_investigator")
        if not forensic or not forensic.structured_output:
            return False
        output = forensic.structured_output
        for key in ["related_party_transactions", "aging_cwip",
                     "auditor_qualifications", "contingent_liabilities_tax"]:
            items = output.get(key, [])
            if any(item.get("severity", "").upper() == "HIGH" for item in items if isinstance(item, dict)):
                return True
        return False
