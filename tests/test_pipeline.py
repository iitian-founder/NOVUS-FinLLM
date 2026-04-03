import pytest
import asyncio
from unittest.mock import patch

from cio_orchestrator import run_orchestrator
from pydantic import BaseModel
from agents.agent_base import AgentRegistry

class DummyRegistry(AgentRegistry):
    def get(self, name):
        # Return none to skip agent logic for pipeline execution
        return None

    def list_agents(self):
        return []

@pytest.mark.asyncio
async def test_orchestrator_pipeline_initiation():
    # Verify the CIO orchestrator can initialize and build a plan under mock conditions
    # Since we don't want to actually ping the LLM, we patch llm_clients (if applicable) or initiate
    
    with patch("cio_orchestrator.generate_strategic_audit_plan") as mock_plan:
        from novus_state import AuditPlan
        mock_plan.return_value = AuditPlan(tasks=[])
        
        state = await run_orchestrator(
            ticker="TCS",
            user_query="Test query",
            context_data="Context string",
            fiscal_year="FY24",
            registry=DummyRegistry()
        )
        
        assert state is not None
        assert state.audit_plan is not None
        assert state.user_context.ticker == "TCS"
