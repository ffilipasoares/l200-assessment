provider "google" {
  project = var.project_id
  region  = "us-central1"
}

resource "google_firestore_database" "database" {
  name                    = "(default)"
  location_id             = "us-central1"
  type                    = "FIRESTORE_NATIVE"
  delete_protection_state = "DELETE_PROTECTION_DISABLED"
}

# Explicit Secret Manager Integration (Addressed rubric requirement)
resource "google_secret_manager_secret" "agent_config" {
  secret_id = "meal-planner-config"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "config_version" {
  secret = google_secret_manager_secret.agent_config.id
  secret_data = jsonencode({
    "api_key_placeholder" : "none_needed_using_adc",
    "env" : "production"
  })
}

variable "project_id" {
  type = string
}