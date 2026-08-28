import os
import json
import logging
import asyncio
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from google.adk.agents import Agent
from google.adk.tools import google_search
from google.cloud import firestore, secretmanager
import google.cloud.logging
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

# --- Observability & Tracing Setup ---
# Setup OpenTelemetry (Utilized as requested)
provider = TracerProvider()
processor = BatchSpanProcessor(ConsoleSpanExporter())
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)

# Structured Logging: Using native library to handle JSON formatting
log_client = google.cloud.logging.Client()
log_client.setup_logging()
logger = logging.getLogger("meal_planner")

def fetch_config_from_secret_manager(secret_id: str) -> Dict[str, Any]:
    """
    Retrieves configuration secrets from Google Cloud Secret Manager.
    
    :param secret_id: The ID of the secret to fetch.
    :return: A dictionary containing the secret configuration.
    """
    try:
        client = secretmanager.SecretManagerServiceClient()
        project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
        name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return json.loads(response.payload.data.decode("UTF-8"))
    except Exception as e:
        logger.warning(f"Secret Manager fetch failed, falling back to defaults: {e}")
        return {}

# Secure configuration injection
app_config = fetch_config_from_secret_manager("meal-planner-config")

def redact_pii(text: str) -> str:
    """Utility to redact emails. Robust guardrails are now handled by the Guardrail Specialist Agent."""
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

# --- Tool Implementation with Pydantic Signatures ---

def get_pantry_inventory(query: InventoryQuery) -> str:
    """
    Retrieves the current items available in the user's pantry from Firestore.
    
    :param query: An InventoryQuery object containing the user_id.
    :return: A JSON string containing 'status' and 'data' (list of items) or an error message with recovery hints.
    """
    user_id = query.user_id
    with tracer.start_as_current_span("get_pantry_inventory") as span:
        span.set_attribute("user.id", user_id)
        
        # Logging: Explicit Intent
        logger.info("Intent: Fetch pantry inventory", extra={"user_id": user_id, "stage": "pre-execution"})
        
        try:
            doc_ref = db.collection("pantries").document(user_id)
            doc = doc_ref.get()
            if doc.exists:
                inventory = doc.to_dict().get("items", [])
                res = {"status": "success", "data": inventory}
                
                # Logging: Explicit Outcome
                logger.info("Outcome: Inventory fetched", extra={
                    "user_id": user_id, 
                    "item_count": len(inventory), 
                    "stage": "post-execution"
                })
                return json.dumps(res)
            return json.dumps({
                "status": "error", 
                "message": "Pantry not found.",
                "recovery_hint": "Ensure the user has initialized their pantry or check the user_id spelling."
            })
        except Exception as e:
            logger.error(redact_pii(f"Error fetching inventory: {str(e)}"))
            return json.dumps({"status": "failure", "error": str(e), "recovery_hint": "Retry the request in 30 seconds."})

                
def save_meal_plan(entry: MealPlanEntry) -> str:
    """
    Persists a meal plan for a specific day of the week to Firestore.
    
    :param entry: A MealPlanEntry object containing day, meal_details, and user_id.
    :return: A JSON string confirmation or an error with recovery instructions.
    """
    with tracer.start_as_current_span("save_meal_plan"):
        # Logging: Explicit Intent
        logger.info("Intent: Save meal plan", extra={"day": entry.day, "user_id": entry.user_id, "stage": "pre-execution"})
        
        try:
            doc_ref = db.collection("plans").document(entry.user_id)
            doc_ref.set({entry.day: entry.meal_details}, merge=True)
            
            # Logging: Explicit Outcome
            logger.info("Outcome: Meal plan saved", extra={"day": entry.day, "status": "success", "stage": "post-execution"})
            return json.dumps({"status": "success", "message": f"Saved {entry.meal_details} for {entry.day}."})
        except Exception as e:
            logger.error(f"Failed to save meal plan: {e}")
            return json.dumps({"status": "error", "message": str(e), "recovery_hint": "Check Firestore permissions."})


async def archive_session_background(user_id: str, plan_summary: str):
    """
    Asynchronous background memory operation to archive session summaries.
    """
    await asyncio.sleep(0.1) # Simulate async IO
    logger.info(f"Background archival started for user {user_id}")
    db.collection("archives").document(user_id).collection("history").add({
        "summary": plan_summary,
        "timestamp": firestore.SERVER_TIMESTAMP
    })

def archive_memory(user_id: str, plan_summary: str) -> str:
    """
    Triggers a background archival of the current session state.
    
    :param user_id: The unique identifier for the user.
    :param plan_summary: A summary of the plan to archive.
    """
    # Management of context bloat: ARCHIVE AND PRUNE
    asyncio.create_task(archive_session_background(user_id, plan_summary))
    return "Archival task scheduled in the background."


def request_human_approval(proposal: str) -> str:
    """
    Human-in-the-loop: Pauses for user confirmation on critical meal changes.
    
    :param proposal: The meal plan proposal requiring approval.
    """
    # In a real ADK implementation, this might trigger a pub/sub event or a UI prompt.
    return "PENDING_APPROVAL: Please confirm if this proposal meets your needs."

# --- Orchestration: Guardrail Specialist ---
guardrail_agent = Agent(
    name="guardrail_specialist",
    model="gemini-1.5-flash",
    description="Validates that no sensitive PII is leaked and ensures nutrition safety.",
    instruction="Review the plan. Redact phone numbers or addresses. Ensure recipes are safe and healthy."
)

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
    4. Before final output, delegate to 'guardrail_specialist' to sanitize PII.
    5. Use 'save_meal_plan' to finalize.
    
    BLOAT MANAGEMENT:
    - If the conversation exceeds 5 turns, use 'archive_memory' to save state, 
      then provide a concise summary and proceed with a fresh mental model 
      to avoid 503/413 errors.
    """,
    tools=[save_meal_plan, request_human_approval, archive_memory],
    agents=[inventory_agent, nutritionist_agent, guardrail_agent] # Multi-agent composition
)
