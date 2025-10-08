#!/bin/bash

TOPIC_NAME="looker-studio-pro-delta-file-info"
GCS_SERVICE_ACCOUNT_EMAIL="service-834967602665@gs-project-accounts.iam.gserviceaccount.com"
WORKFLOW_PROJECT_ID="proj-sales-recommender-dev"
BUCKET_NAME="construct_connect_full_dump"
WORKFLOW_SERVICE_EMAIL="195063057478-compute@developer.gserviceaccount.com"
TRIGGER_NAME="trigger-cloud-functions-workflow"
LOCATION="us-west1"
WORKLOW_NAME="cloud_functions_workflow"

gcloud pubsub topics create "$TOPIC_NAME"

gcloud pubsub topics add-iam-policy-binding \
    projects/${WORKFLOW_PROJECT_ID}/topics/${TOPIC_NAME} \
    --member="serviceAccount:${WORKFLOW_SERVICE_EMAIL}" \
    --role="roles/pubsub.subscriber"

gcloud pubsub topics add-iam-policy-binding \
    projects/${WORKFLOW_PROJECT_ID}/topics/${TOPIC_NAME} \
    --member="serviceAccount:${WORKFLOW_SERVICE_EMAIL}" \
    --role="roles/pubsub.subscriber"


RESULT=$(gcloud eventarc triggers list  --filter="name.scope(trigger):trigger-cloud-functions-workflow")

if [ "${RESULT}" == "" ]
then
  echo "Trigger ${TRIGGER_NAME} does not exist, creating..."
  gcloud eventarc triggers create ${TRIGGER_NAME} \
--location=${LOCATION} \
--service-account=${WORKFLOW_SERVICE_EMAIL} \
--transport-topic=projects/${WORKFLOW_PROJECT_ID}/topics/${TOPIC_NAME} \
--destination-workflow=${WORKLOW_NAME} \
--destination-workflow-location=${LOCATION} \
--event-filters="type=google.cloud.pubsub.topic.v1.messagePublished"
fi
