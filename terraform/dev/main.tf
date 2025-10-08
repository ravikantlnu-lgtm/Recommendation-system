# Provider Configuration

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "4.61.0"
    }
  }
}
provider "google" {
  project = var.project_id
  region  = var.region
}

# Create a Service Account for the Workflow
  resource "google_service_account" "workflow_service_account" {
    account_id   = "workflow-service-account"
    display_name = "workflow-service-account"
    project      = var.project_id
    depends_on = [ module.enable_apis_dev ]
  }

#Workflow invoker Role
resource "google_project_iam_member" "workflow_service_account_role" {
  for_each = var.workflow_roles
  project = var.project_id
  role    = "roles/${each.key}"
  member  = "serviceAccount:${google_service_account.workflow_service_account.email}"
  depends_on = [ module.enable_apis_dev ]
  
}

# Cloud Storage Buckets

resource "google_storage_bucket" "sales_recommender_bucket" {
  name     = "sales_recommender_${var.deployment}_bucket"
  location = "us"
  depends_on = [ module.enable_apis_dev ]

}

resource "google_storage_bucket" "sales_rec_staging" {
  name     = "sales-rec-staging"
  location = "us"
  depends_on = [ module.enable_apis_dev ]

}


# Output the Service Account Email (Optional)
output "workflow_service_account_email" {
  value = google_service_account.workflow_service_account.email
}


# # Cloud Tasks Queue Configuration
# resource "google_cloud_tasks_queue" "project-queue" {
#   name     = "project-queue"
#   project  = var.project_id
#   location = var.region

#   rate_limits {
#     max_concurrent_dispatches = 1000
#     max_dispatches_per_second = 1.0
#   }

#   retry_config {
#     max_attempts  = 100
#     max_backoff   = "3600s"
#     max_doublings = 16
#     min_backoff   = "0.100s"
#   }

#   stackdriver_logging_config {
#     sampling_ratio = 1.0
#   }
#   depends_on = [ module.enable_apis_dev ]


# }


resource "google_bigquery_dataset" "sales_recommender_dev" {
  dataset_id = "sales_recommender_dev"
  project    = var.project_id
  location   = "us-west1"
  depends_on = [ module.enable_apis_dev ]

}



# Enabling APIs for the dev project
module "enable_apis_dev" {
  source  = "terraform-google-modules/project-factory/google//modules/project_services"
  version = "~> 16.0.1"

  project_id                  = var.project_id
  activate_apis               = local.apis_to_enable # Reference to the APIs defined in locals.tf
  disable_services_on_destroy = false                # Ensure APIs are not disabled on destroy
}


resource "google_secret_manager_secret" "secrets_fbm_sales" {
    for_each    =  var.secret_ids
    project     =  var.project_id
    secret_id   = "${each.key}"

    replication {
        automatic = true
    }
   
    depends_on = [ module.enable_apis_dev ]

}


data "google_compute_default_service_account" "default" {
}


resource "google_project_iam_member" "compute_service_account_role" {
  for_each = var.compute_service_account_roles
  project = var.project_id
  role    = "roles/${each.key}"
  member  = "serviceAccount:${data.google_compute_default_service_account.default.email}"
  depends_on = [ module.enable_apis_dev ]
}


resource "google_apikeys_key" "gemini_api_key" {
   name         = "gemini-api"
   display_name = "gemini-api"
   restrictions {
    api_targets {
      service = "generativelanguage.googleapis.com"
      methods = ["GET*"]
    }

  }
}

