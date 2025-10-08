# GCP Workflow Triggered by GCS File Upload

This workflow is triggered when a file is uploaded to a Google Cloud Storage (GCS) bucket. The workflow uses Eventarc to listen for file upload events and then triggers a Cloud Function.

## Workflow Steps

 1. **Log Event**: Logs the event details.
 2. **Trigger Cloud Function**: Sends an HTTP POST request to a specified Cloud Function URL with the event details.
 3. **Log Response**: Logs the response from the Cloud Function.
 4. **Return**: Returns a completion message.


Setting Up Eventarc
To set up Eventarc to trigger this workflow when a file is uploaded to a GCS bucket, follow these steps:

 1.**Create an Eventarc Trigger**:
    gcloud eventarc triggers create my-trigger \
    --destination-workflow=projects/YOUR_PROJECT_ID/locations/YOUR_LOCATION/workflows/YOUR_WORKFLOW_NAME \
    --event-filters="type=google.cloud.storage.object.v1.finalized" \
    --event-filters="bucket=YOUR_BUCKET_NAME" \
    --service-account=YOUR_SERVICE_ACCOUNT_EMAIL

**Required Permissions:**

 roles/eventarc.eventReceiver on the workflow's service account.

 roles/storage.objectViewer on the GCS bucket for the workflow's service account.

 roles/workflows.invoker on the workflow for the Eventarc service account.

**Permissions**
Ensure the following permissions are granted:

 1.**Eventarc Service Account**:

 roles/eventarc.eventReceiver
 
 roles/workflows.invoker

 2.**Workflow Service Account**:

roles/storage.objectViewer

**Conclusion**

 This setup ensures that whenever a file is uploaded to the specified GCS bucket, the workflow is triggered, logs the event, triggers a Cloud Function, logs the response, and returns a completion message.

