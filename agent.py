import os
from google.adk.agents import Agent
from google.adk.tools import google_search

# Tool & Interface Design: Defining clear, type-hinted functions with docstrings
# for the Gemini model to identify as tools.

def get_pantry_inventory() -> str:
    """
    Retrieves the current items available in the user's pantry.
    Used to ensure meal plans use existing ingredients.
    """
    # Integration Point: In production, this would query a Firestore database.
    return "Current items: Chicken breast, Spinach, Olive oil, Rice, Quinoa, Garlic."

def save_meal_plan(day: str, meal_details: str) -> str:
    """
    Persists a meal plan for a specific day of the week.
    Args:
        day: The day of the week (e.g., 'Monday').
        meal_details: The name and brief description of the meal.
    """
    # Context & Memory: This tool allows the agent to 'remember' the plan
    # across turns by writing to a persistent store.
    return f"Successfully saved {meal_details} for {day}."

# Orchestration & Logic: The LlmAgent coordinates between tools and the user.
meal_planner_agent = Agent(
    name="meal_planner_pro",
    model="gemini-1.5-pro",  # Enterprise-grade Gemini resource
    description="A professional meal planning assistant that uses pantry data and search.",
    instruction="""
    You are an expert nutritionist. Your goal is to help users plan their weekly meals.
    
    Workflow:
    1. Check the user's pantry inventory using 'get_pantry_inventory'.
    2. Ask the user for their dietary preferences or health goals.
    3. Use 'google_search' to find recipes that match their pantry items and goals.
    4. Propose a plan and use 'save_meal_plan' to finalize choices for each day.
    5. Finally, provide a grocery list for missing ingredients.
    
    Be concise, helpful, and prioritize health-conscious suggestions.
    """,
    tools=[get_pantry_inventory, save_meal_plan, google_search]
)

# Observability & Tracing: ADK automatically logs tool calls and reasoning steps.
# When running via 'adk run', execution traces are visible in the terminal/UI.
