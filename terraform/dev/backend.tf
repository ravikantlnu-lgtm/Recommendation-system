terraform {
  backend "gcs" {
    bucket = "fbm-sales-gcp-state-bucket-dev"
    prefix = "terraform/dev-state"
  }
}

