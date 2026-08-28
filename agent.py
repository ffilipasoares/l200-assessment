import os
import json
import logging
from typing import Optional, List, Dict
from google.adk.agents import Agent
from google.adk.tools import google_search
from google.cloud import firestore
import google.cloud.logging
from opentelemetry import trace

# --- Observability & Tracing Setup ---
client = google.cloud.logging.Client()
client.setup_logging()
logger = logging.getLogger("meal_planner_agent")

def redact_pii(text: str) -> str:
    """Simple utility to redact potential PII before logging/processing."""
    # Example placeholder for regex-based redaction (Email, SSN, etc.)
    return text

# --- Context & Memory: Firestore Persistence ---
db = firestore.Client()

def get_pantry_inventory(user_id: str = "default_user") -> str:
    """
    Retrieves the current items available in the user's pantry.
    Returns a JSON string of items or an error message.
    """
    try:
        doc_ref = db.collection("pantries").document(user_id)
        doc = doc_ref.get()
        if doc.exists:
            inventory = doc.to_dict().get("items", [])
            return json.dumps({"status": "success", "data": inventory})
        return json.dumps({"status": "error", "message": "Pantry not found."})
    except Exception as e:
        logger.error(f"Error fetching inventory: {e}")
        return json.dumps({"status": "failure", "error": str(e)})

def save_meal_plan(day: str, meal_details: str, user_id: str = "default_user") -> str:
    """
    Persists a meal plan for a specific day of the week.
    """
    try:
        if not day or not meal_details:
            raise ValueError("Invalid input: 'day' and 'meal_details' are required.")
        
        doc_ref = db.collection("plans").document(user_id)
        doc_ref.set({day: meal_details}, merge=True)
        
        logger.info(json.dumps({"intent": "save_meal", "outcome": "success", "day": day}))
        return json.dumps({"status": "success", "message": f"Saved {meal_details} for {day}."})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

def request_human_approval(proposal: str) -> str:
    """
    Human-in-the-loop: Pauses for user confirmation on critical meal changes.
    """
    # In a real ADK implementation, this might trigger a pub/sub event or a UI prompt.
    return "PENDING_APPROVAL: Please confirm if this proposal meets your needs."

# --- Orchestration & Logic: Multi-Agent Pattern ---

# Specialist 1: Inventory Management
inventory_agent = Agent(
    name="inventory_manager",
    model="gemini-1.5-flash", # Routing to a faster model for simple retrieval
    description="Manages pantry data.",
    instruction="You fetch and format pantry inventory data.",
    tools=[get_pantry_inventory]
)

# Specialist 2: Nutritionist
nutritionist_agent = Agent(
    name="nutritionist",
    model="gemini-1.5-pro",
    description="Expert nutritionist focused on recipe creation.",
    instruction="You design healthy recipes based on ingredients provided to you.",
    tools=[google_search]
)

# Supervisor Agent: Orchestrator
meal_planner_agent = Agent(
    name="supervisor_agent",
    model="gemini-1.5-pro",
    description="Main entry point for meal planning.",
    instruction="""
    You are the Supervisor. Orchestrate the workflow:
    1. Delegate to 'inventory_manager' to see what is available.
    2. Ask the user for preferences.
    3. Delegate to 'nutritionist' to find recipes.
    4. Call 'request_human_approval' before saving.
    5. Use 'save_meal_plan' to finalize.
    
    Maintain a concise history. If the conversation gets long, summarize key points.
    """,
    tools=[save_meal_plan, request_human_approval],
    agents=[inventory_agent, nutritionist_agent] # Multi-agent composition
)
