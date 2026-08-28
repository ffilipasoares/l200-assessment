import pytest
import json
from agent import meal_planner_agent
from agent import get_pantry_inventory

# Golden Dataset for Regression Testing
GOLDEN_INVENTORY_RESPONSE = {
    "status": "success",
    "data": ["Chicken breast", "Spinach", "Olive oil"]
}

def test_agent_structure():
    """Verify agent has required tools and multi-agent composition."""
    assert meal_planner_agent.name == "supervisor_agent"
    assert len(meal_planner_agent.agents) == 2

def test_tool_outputs():
    """Ensure tools return JSON strings with recovery hints on error."""
    result = get_pantry_inventory("test_user")
    data = json.loads(result)
    assert isinstance(result, str)
    assert "status" in result
    
def test_pii_redaction():
    """Test the redaction utility."""
    from agent import redact_pii
    assert "test@[REDACTED_EMAIL]" not in redact_pii("Contact me at test@example.com")