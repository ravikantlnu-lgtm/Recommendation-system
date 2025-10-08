terraform {
  backend "gcs" {
    bucket = "fbm-sales-gcp-state-bucket-prod"
    prefix = "terraform/prod-state"
  }
}
