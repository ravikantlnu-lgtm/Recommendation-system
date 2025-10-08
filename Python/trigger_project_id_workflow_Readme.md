
# Trigger Google Cloud Workflow for a Single Delta File

This script triggers a Google Cloud Workflow with input data, fetches metadata from a Google Cloud Storage (GCS) bucket, encodes it to Base64, and passes it as input to the workflow. It is designed to reprocess a single delta file through the specified workflow.

## Prerequisites

1. **Python Environment**:
    - Ensure you have Python 3.7 or later installed.

2. **Google Cloud SDK**:
    - Install and configure the [Google Cloud SDK](https://cloud.google.com/sdk/docs/install).
    - Authenticate using:
      ```bash
      gcloud auth application-default login
      ```

3. **Required Python Libraries**:
    - Install the required libraries using `pip`:
      ```bash
      pip install google-cloud-workflows google-cloud-storage
      ```

4. **Google Cloud Workflow**:
    - Ensure the workflow you want to trigger is deployed and accessible.

5. **Permissions**:
    - The service account used must have the following permissions:
      - `roles/workflows.invoker` for triggering the workflow.
      - `roles/storage.objectViewer` for accessing the GCS bucket and blob.

## Usage

### Running the Script

1. Clone or download the repository containing the script.

2. Navigate to the directory containing the script:
    ```bash
    cd fbmSalesRecommender/Python
    ```

3. Run the script with the required arguments:
    ```bash
    python trigger_project_id_workflow.py --project-id="your-project-id" --blob-name="path/to/your-delta-file.xml"
    ```

### Optional Arguments

- `--location`: The location of the workflow. Default is `us-west1`.
- `--workflow-id`: The ID of the workflow to execute. Default is `cloud_functions_workflow`.
- `--bucket-name`: The name of the GCS bucket. Default is `construct_connect_full_dump`.

### Example Commands

#### Using Default Values
```bash
python trigger_project_id_workflow.py --project-id="my-project-id" --blob-name="delta/my-delta-file.xml"
```

#### Customizing All Parameters
```bash
python trigger_project_id_workflow.py \
     --project-id="my-project-id" \
     --location="us-central1" \
     --workflow-id="my-custom-workflow-id" \
     --bucket-name="my-custom-bucket" \
     --blob-name="Delta/my-delta-file.xml"
```

### Output

- The script will print the fetched metadata, Base64-encoded data, and the workflow execution result to the console.
- If the workflow execution is successful, the final result will be displayed.
- If the workflow execution fails, an error message will be printed.

## Script Workflow

1. **Fetch Metadata**:
    - Retrieves metadata (e.g., file name, size, creation time) of the specified blob from the GCS bucket.

2. **Encode Metadata**:
    - Encodes the metadata into a Base64 string.

3. **Trigger Workflow**:
    - Sends the Base64-encoded metadata as input to the specified Google Cloud Workflow.

4. **Wait for Completion**:
    - Polls the workflow execution status until it completes or fails.

5. **Display Results**:
    - Prints the workflow execution result or error message.

## Troubleshooting

- **Authentication Issues**:
  - Ensure you have authenticated using:
     ```bash
     gcloud auth application-default login
     ```

- **Permission Errors**:
  - Verify that the service account has the required permissions.

- **Blob Not Found**:
  - Ensure the `--bucket-name` and `--blob-name` arguments are correct.

- **Workflow Execution Errors**:
  - Check the workflow logs in the Google Cloud Console for more details.

