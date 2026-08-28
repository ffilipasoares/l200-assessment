import os
import json
import logging
from typing import Optional, List, Dict
from pydantic import BaseModel, Field
from google.adk.agents import Agent
from google.adk.tools import google_search
from google.cloud import firestore, secretmanager
import google.cloud.logging
from opentelemetry import trace, baggage
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

# --- Observability & Tracing Setup ---
# Setup OpenTelemetry (Utilized as requested)
provider = TracerProvider()
processor = BatchSpanProcessor(ConsoleSpanExporter())
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)

client = google.cloud.logging.Client()
client.setup_logging()
logger = logging.getLogger("meal_planner_agent")

def redact_pii(text: str) -> str:
    """Actively redacts email patterns from strings to protect PII."""
    import re
    email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    return re.sub(email_pattern, "[REDACTED_EMAIL]", text)

# --- Context & Memory: Firestore Persistence ---
db = firestore.Client()

# --- Interface Design: Explicit JSON Schemas via Pydantic ---
class InventoryQuery(BaseModel):
    user_id: str = Field(..., description="The unique identifier for the user, e.g., 'user_123'.")

class MealPlanEntry(BaseModel):
    day: str = Field(..., description="The day of the week, e.g., 'Monday'.")
    meal_details: str = Field(..., description="Description of the meal and ingredients.")
    user_id: str = Field(default="default_user", description="The unique identifier for the user.")


def get_pantry_inventory(user_id: str = "default_user") -> str:
    """
    Retrieves the current items available in the user's pantry from Firestore.
    
    :param user_id: The unique identifier for the user.
    :return: A JSON string containing 'status', and 'data' (list of items) or 'error'.
    """
    with tracer.start_as_current_span("get_pantry_inventory") as span:
        span.set_attribute("user.id", user_id)
        try:
            doc_ref = db.collection("pantries").document(user_id)
            doc = doc_ref.get()
            if doc.exists:
                res = {"status": "success", "data": inventory}
                logger.info(redact_pii(f"Inventory fetched for {user_id}: {inventory}"))
                return json.dumps(res)
            return json.dumps({
                "status": "error", 
                "message": "Pantry not found.",
                "recovery_hint": "Ensure the user has initialized their pantry or check the user_id spelling."
            })
        except Exception as e:
            logger.error(redact_pii(f"Error fetching inventory: {str(e)}"))
            return json.dumps({"status": "failure", "error": str(e), "recovery_hint": "Retry the request in 30 seconds."})

                

def save_meal_plan(day: str, meal_details: str, user_id: str = "default_user") -> str:
    """
    Persists a meal plan for a specific day of the week to Firestore.
    
    :param day: The day of the week to save the plan for.
    :param meal_details: The meal description.
    :param user_id: The unique identifier for the user.
    :return: A JSON string confirmation or error with recovery instructions.
    """
    with tracer.start_as_current_span("save_meal_plan"):
        try:
            if not day or not meal_details:
                return json.dumps({
                    "status": "error", 
                    "message": "Missing required fields.",
                    "recovery_hint": "Please provide both 'day' and 'meal_details'."
                })
            
            doc_ref = db.collection("plans").document(user_id)
            doc_ref.set({day: meal_details}, merge=True)
            
            logger.info(json.dumps({"intent": "save_meal", "outcome": "success", "day": redact_pii(day)}))
            return json.dumps({"status": "success", "message": f"Saved {meal_details} for {day}."})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e), "recovery_hint": "Check Firestore permissions."})


def request_human_approval(proposal: str) -> str:
    """
    Human-in-the-loop: Pauses for user confirmation on critical meal changes.
    
    :param proposal: The meal plan proposal requiring approval.

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
    2. Delegate to 'nutritionist' to find recipes based on inventory.
    3. Call 'request_human_approval' before saving.
    4. Use 'save_meal_plan' to finalize.
    
    CONTEXT MANAGEMENT:
    - Maintain a concise history. If the conversation exceeds 5 turns, summarize the current plan and pantry state, then clear old history to avoid 503 errors.
    """,
    tools=[save_meal_plan, request_human_approval],
    agents=[inventory_agent, nutritionist_agent] # Multi-agent composition
)
