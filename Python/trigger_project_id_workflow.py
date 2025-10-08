"""
Triggers a Google Cloud Workflow with specified parameters.

This script triggers a Google Cloud Workflow with input data and waits for its completion.
It also fetches metadata from a GCS bucket, encodes it to Base64, and passes it as input to the workflow.

Examples:
    Run with default values:
        $ python trigger_project_id_workflow.py --project-id="my-project-id" --blob-name="folder/my-blob.xml"

    Run with all custom values:
        $ python trigger_project_id_workflow.py \
            --project-id="my-project-id" \
            --location="us-central1" \
            --workflow-id="my-workflow-id" \
            --bucket-name="my-bucket" \
            --blob-name="folder/my-blob.xml"

Returns:
    None. Prints the workflow execution result to stdout.
"""

import time
import json
import base64
import argparse
from datetime import datetime
from google.cloud import workflows_v1
from google.cloud.workflows import executions_v1
from google.cloud.workflows.executions_v1.types import Execution
from google.cloud import storage


def trigger_and_wait_workflow_with_input(project_id: str, location: str, workflow_id: str, workflow_input: dict):
    """Triggers a Google Cloud Workflow with input and waits for its completion."""
    execution_client = executions_v1.ExecutionsClient()
    workflows_client = workflows_v1.WorkflowsClient()
    parent = workflows_client.workflow_path(project_id, location, workflow_id)

    try:
        argument_json = json.dumps(workflow_input)
        response = execution_client.create_execution(
            request={"parent": parent, "execution": {"argument": argument_json}}
        )
        print(f"Created execution: {response.name}")

        execution_finished = False
        backoff_delay = 1
        print("Polling for result...")

        while not execution_finished:
            execution = execution_client.get_execution(request={"name": response.name})
            execution_finished = execution.state != Execution.State.ACTIVE

            if not execution_finished:
                print(f"- Waiting for results... (Current state: {execution.state.name})")
                time.sleep(backoff_delay)
                backoff_delay *= 2
            else:
                print(f"Execution finished with state: {execution.state.name}")
                print(f"Execution results: {execution.result}")
                return execution.result

    except Exception as e:
        print(f"An error occurred: {e}")
        raise f"An error occurred: {e}"    


def fetch_gcs_metadata(bucket_name, blob_name):
    """Fetches metadata of a GCS blob."""
    client = storage.Client()
    bucket = client.get_bucket(bucket_name)
    blob = bucket.get_blob(blob_name)
    if blob:
        time_created = blob.time_created
        formatted_time_created = time_created.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        metadata = {
            "name": blob.name,
            "size": blob.size,
            "timeCreated": formatted_time_created,
            "bucket": blob.bucket.name
        }
        return metadata
    else:
        raise "error : Blob not found"


def encode_to_base64(data):
    """Encodes a Python dictionary to a Base64 string."""
    return base64.b64encode(json.dumps(data).encode('utf-8')).decode('utf-8')


def main():
    parser = argparse.ArgumentParser(description="Trigger a Google Cloud Workflow with input data.")
    parser.add_argument("--project-id", type=str, required=True, help="Google Cloud project ID.")
    parser.add_argument("--location", type=str, default="us-west1", help="Location of the workflow.")
    parser.add_argument("--workflow-id", type=str, default="cloud_functions_workflow", help="ID of the workflow to execute.")
    parser.add_argument("--bucket-name", type=str, default="construct_connect_full_dump", help="Name of the GCS bucket.")
    parser.add_argument("--blob-name", type=str, required=True, help="Name of the blob in the GCS bucket.")


    args = parser.parse_args()

    metadata = fetch_gcs_metadata(args.bucket_name, args.blob_name)
    print("Fetched metadata:", metadata)

    encoded_data = encode_to_base64(metadata)
    print(f"Encoded data: {encoded_data}")

    workflow_input_data = {
        "data": {
            "message": {
                "data": encoded_data
            }
        }
    }

    result = trigger_and_wait_workflow_with_input(args.project_id, args.location, args.workflow_id, workflow_input_data)
    if result:
        print("Workflow execution successful. Final result:")
        print(result)
    else:
        print("Workflow execution failed or encountered an error.")


if __name__ == "__main__":
    main()
