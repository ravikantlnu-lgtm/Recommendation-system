# Deployment Scripts

This directory contains scripts for deploying and configuring various components of the FBM Sales Recommender system.

## Scripts

### Cloud Function Deployment

-   **`deploy_cloud_function.py`**: A Python script that deploys Google Cloud Functions. It handles copying the main function file to `main.py` and uses `gcloud` to deploy with configurable parameters like function name, entry point, runtime, region, memory, CPU, concurrency, timeout, and service account.
-   **`call_deploy_cloud_function.sh`**: A shell script that uses `deploy_cloud_function.py` to deploy multiple Cloud Functions. It sets common variables and calls the Python script with specific parameters for each function.

### Cloud Task Queue Creation

-   **`create_cloud_task_queue.py`**: A Python script to create Google Cloud Tasks queues.
-   **`create_cloud_task_dev.sh`**: Shell script that uses `create_cloud_task_queue.py` to create a Cloud Task queue named `project-queue-dev` in the dev environment (`proj-sales-recommender-dev`). It first checks if the queue already exists.
-   **`create_cloud_task_prod.sh`**: Shell script that uses `create_cloud_task_queue.py` to create a Cloud Task queue named `project-queue-prod` in the prod environment (`proj-sales-recommender-prod`). It first checks if the queue already exists.

### Pub/Sub Topic and Eventarc Trigger Creation

-   **`create_pubsub_topic_dev.sh`**: Shell script to create a Pub/Sub topic and an Eventarc trigger for the dev environment. The trigger is configured to listen for messages published to the topic and invoke a Cloud Workflow.
-   **`create_pubsub_topic_prod.sh`**: Shell script to create a Pub/Sub topic and an Eventarc trigger for the prod environment. Similar to the dev script, it sets up a trigger for a Cloud Workflow based on Pub/Sub messages.

### Cloud Storage Notification Creation

-   **`create_storage_notification_dev.sh`**: Shell script to create a Google Cloud Storage notification for the dev environment. This script configures a GCS bucket to send a notification to a Pub/Sub topic when new objects are finalized in the bucket. It also grants the GCS service account the necessary permissions to publish to the topic.
-   **`create_storage_notification_prod.sh`**: Shell script to create a Google Cloud Storage notification for the prod environment. It performs the same actions as the dev script but for the production GCS bucket and Pub/Sub topic.

### Requirements

-   **`requirements.txt`**: A file listing the Python dependencies required by the Python scripts in this directory. These dependencies are typically installed using `pip install -r requirements.txt`.

## General Usage

Before running deployment scripts, ensure you have:
1.  Authenticated with Google Cloud SDK (`gcloud auth login`, `gcloud auth application-default login`).
2.  Set the correct Google Cloud project (`gcloud config set project <YOUR_PROJECT_ID>`).
3.  Installed necessary dependencies (e.g., `pip install -r requirements.txt` for Python scripts).

Refer to the individual scripts for specific environment variables or parameters that might need to be set. For example, the `call_deploy_cloud_function.sh` script expects an `ENVIRONMENT` variable to be set (e.g., `dev` or `prod`).

The setup and deployment section in the main [README.md#setup--deployment](/#setup--deployment) provides higher-level context on how these deployment scripts fit into the overall project setup.
