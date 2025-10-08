#!/bin/bash

PROJECT_ID="proj-sales-recommender-dev"
LOCATION="us-west1"
QUEUE_NAME="project-queue-dev"

# Install required Python packages
pip install -r requirements.txt

RESULT=$(gcloud tasks queues list --location=us-west1  --filter="name.scope(task):project-queue-dev")

if [ "${RESULT}" == "" ]
then
  python create_cloud_task_queue.py \
            --project-id="${PROJECT_ID}" \
            --location="${LOCATION}" \
            --queue-name="${QUEUE_NAME}"
fi