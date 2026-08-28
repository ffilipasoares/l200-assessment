import pytest
from agent import meal_planner_agent

def test_agent_structure():
    """Verify agent has required tools and multi-agent composition."""
    assert meal_planner_agent.name == "supervisor_agent"
    assert len(meal_planner_agent.agents) == 2

def test_tool_outputs():
    """Ensure tools return JSON strings for LLM stability."""
    from agent import get_pantry_inventory
    result = get_pantry_inventory("test_user")
    assert isinstance(result, str)
    assert "status" in result