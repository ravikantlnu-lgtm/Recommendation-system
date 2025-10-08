
locals {
  apis_to_enable = [
    "aiplatform.googleapis.com",              # Vertex AI API
    "analyticshub.googleapis.com",            # Analytics Hub API
    "artifactregistry.googleapis.com",        # Artifact Registry API
    "bigquery.googleapis.com",                # BigQuery API
    "bigqueryconnection.googleapis.com",      # BigQuery Connection API
    "bigquerydatapolicy.googleapis.com",      # BigQuery Data Policy API
    "bigquerymigration.googleapis.com",       # BigQuery Migration API
    "bigqueryreservation.googleapis.com",     # BigQuery Reservation API
    "bigquerystorage.googleapis.com",         # BigQuery Storage API
    "cloudaicompanion.googleapis.com",        # Gemini for Google Cloud API
    "cloudapis.googleapis.com",               # Google Cloud APIs
    "cloudbuild.googleapis.com",              # Cloud Build API
    "cloudfunctions.googleapis.com",          # Cloud Functions API
    "cloudresourcemanager.googleapis.com",    # Cloud Resource Manager API
    "cloudtasks.googleapis.com",              # Cloud Tasks API
    "cloudtrace.googleapis.com",              # Cloud Trace API
    "compute.googleapis.com",                 # Compute Engine API
    "containerregistry.googleapis.com",       # Container Registry API
    "dataform.googleapis.com",                # Dataform API
    "dataplex.googleapis.com",                # Cloud Dataplex API
    "datastore.googleapis.com",               # Cloud Datastore API
    "documentai.googleapis.com",              # Cloud Document AI API
    "eventarc.googleapis.com",                # Eventarc API
    "firebaserules.googleapis.com",           # Firebase Rules API
    "firestore.googleapis.com",               # Cloud Firestore API
    "iam.googleapis.com",                     # Identity and Access Management (IAM) API
    "iamcredentials.googleapis.com",          # IAM Service Account Credentials API
    "logging.googleapis.com",                 # Cloud Logging API
    "monitoring.googleapis.com",              # Cloud Monitoring API
    "notebooks.googleapis.com",               # Notebooks API
    "oslogin.googleapis.com",                 # Cloud OS Login API
    "privilegedaccessmanager.googleapis.com", # Privileged Access Manager API
    "pubsub.googleapis.com",                  # Cloud Pub/Sub API
    "run.googleapis.com",                     # Cloud Run Admin API
    "servicemanagement.googleapis.com",       # Service Management API
    "serviceusage.googleapis.com",            # Service Usage API
    "sql-component.googleapis.com",           # Cloud SQL
    "storage-api.googleapis.com",             # Google Cloud Storage JSON API
    "storage-component.googleapis.com",       # Cloud Storage
    "storage.googleapis.com",                 # Cloud Storage API
    "workflowexecutions.googleapis.com",      # Workflow Executions API
    "workflows.googleapis.com",               # Workflows API
    "secretmanager.googleapis.com",           # Secret Manager API
    "generativelanguage.googleapis.com",      # Gemini API
    "apikeys.googleapis.com"                  # API keys API
  ]
}
