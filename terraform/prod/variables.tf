# variables.tf

variable "project_id" {
  type        = string
  description = "The GCP project ID"
}

variable "region" {
  type        = string
  description = "The GCP region"
  default     = "us-west1"
}

variable "deployment" {
  type        = string
  description = "The deployment environment (e.g., dev, staging, prod)"
}

# New variables for GitHub integration
variable "github_owner" {
  type        = string
  description = "The GitHub account or organization that owns the repository"
}

variable "github_app_repo" {
  type        = string
  description = "The GitHub repository name"
}

variable "disable_services_on_destroy" {
  description = "Whether project services will be disabled when the resources are destroyed"
  type        = bool
  default     = false
}

variable "workflow_roles" {
  description = "Roles to be given to workflow service account"
  type = set(string)
}

variable "secret_ids" {
  description = "List of secret ids"
  type = set(string)
}

variable "compute_service_account_roles" {
  description = "Roles to be given to compute service account"
  type = set(string)
}