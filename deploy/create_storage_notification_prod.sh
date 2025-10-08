TOPIC_NAME="looker-studio-pro-delta-file-info"
GCS_SERVICE_ACCOUNT_EMAIL="service-834967602665@gs-project-accounts.iam.gserviceaccount.com"
WORKFLOW_PROJECT_ID="proj-sales-recommender-prod"
BUCKET_NAME="construct_connect_full_dump"
DODGE_BUCKET_NAME="dodge_full_dump"

gcloud pubsub topics add-iam-policy-binding \
    projects/${WORKFLOW_PROJECT_ID}/topics/${TOPIC_NAME} \
    --member="serviceAccount:${GCS_SERVICE_ACCOUNT_EMAIL}" \
    --role="roles/pubsub.publisher" \
    --project=${WORKFLOW_PROJECT_ID}

gsutil notification create -t projects/${WORKFLOW_PROJECT_ID}/topics/${TOPIC_NAME} -f json -e OBJECT_FINALIZE gs://${BUCKET_NAME}

gsutil notification create -t projects/${WORKFLOW_PROJECT_ID}/topics/${TOPIC_NAME} -f json -e OBJECT_FINALIZE gs://${DODGE_BUCKET_NAME}


