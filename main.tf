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

variable "project_id" {
  type = string
}