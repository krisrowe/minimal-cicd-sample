terraform {
  required_version = ">= 1.0.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

provider "google" {
  project = var.project_id
}

# Minimal resource: just verify the provider connects
data "google_project" "this" {}

output "project_name" {
  value = data.google_project.this.name
}
