# terraform.tfvars

project_id      = "proj-sales-recommender-dev"
region          = "us-west1"
deployment      = "dev"
github_owner    = "fbmsales"
github_app_repo = "fbmSalesRecommender"
workflow_roles  = ["workflows.invoker","cloudfunctions.admin","eventarc.eventReceiver","logging.admin"]
secret_ids      = ["gemini_api_key","dynamics_cred","default-service-account"]
compute_service_account_roles = ["workflows.admin","cloudfunctions.admin","run.invoker","secretmanager.secretAccessor","notebooks.serviceAgent","artifactregistry.admin","storage.admin","editor","aiplatform.notebooks.serviceAgent","aiplatform.user"]