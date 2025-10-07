# Grafana Dashboards Terraform Configuration
# Manages Grafana Cloud dashboards via Terraform

terraform {
  required_providers {
    grafana = {
      source  = "grafana/grafana"
      version = "~> 3.0"
    }
  }
}

# Configure Grafana provider
provider "grafana" {
  url  = var.grafana_url
  auth = var.grafana_api_token
}

# Variables
variable "grafana_url" {
  description = "Grafana instance URL"
  type        = string
  # Example: https://stack-1184667-hm-prod-us-east-2.grafana.net
}

variable "grafana_api_token" {
  description = "Grafana API token (service account token with dashboard write permissions)"
  type        = string
  sensitive   = true
}

variable "grafana_folder_title" {
  description = "Folder name in Grafana for dashboards"
  type        = string
  default     = "MLS Match Scraper"
}

# Create folder for dashboards
resource "grafana_folder" "mls_scraper" {
  title = var.grafana_folder_title
}

# Deploy Overview Dashboard
resource "grafana_dashboard" "scraper_overview" {
  folder      = grafana_folder.mls_scraper.id
  config_json = file("${path.module}/../grafana/dashboards/scraper-overview.json")

  overwrite = true

  lifecycle {
    ignore_changes = [
      # Ignore user-made changes in UI
      config_json,
    ]
  }
}

# Deploy Errors Dashboard
resource "grafana_dashboard" "scraper_errors" {
  folder      = grafana_folder.mls_scraper.id
  config_json = file("${path.module}/../grafana/dashboards/scraper-errors.json")

  overwrite = true

  lifecycle {
    ignore_changes = [
      # Ignore user-made changes in UI
      config_json,
    ]
  }
}

# Outputs
output "overview_dashboard_url" {
  description = "URL to the overview dashboard"
  value       = grafana_dashboard.scraper_overview.url
}

output "errors_dashboard_url" {
  description = "URL to the errors dashboard"
  value       = grafana_dashboard.scraper_errors.url
}

output "folder_uid" {
  description = "UID of the dashboards folder"
  value       = grafana_folder.mls_scraper.uid
}
