import logging
from datetime import datetime

import functions_framework
from config import get_settings
from services import BigQueryManager
from logging_config import log_default, log_error
import traceback
import json
import os
import io

 # Load settings
settings = get_settings()

@functions_framework.http
def handle_workflow_failure(request):
    try:
        request_json = request.get_json(silent=True)
        if request_json:
            event = request_json.get("event", "No event provided")
        else:
            log_error(
                function_name="handle_workflow_failure",
                endpoint="workflow-failure",
                log_message="No JSON payload received.",
            )
            return {
                "status": "failed",
                "log_message": "No JSON payload received.",
            }

        project_id = settings.PROJECT_ID
        dataset_id = settings.BIGQUERY_DATASET
        workflow_failure_events_table_id = settings.WORKFLOW_FAILURE_EVENTS_TABLE_ID

        workflow_name = event.get("workflow_name")
        failure_point = event.get("failure_point")
        error_type = event.get("error_type")
        error_message = event.get("error_message")
        input_data = event.get("input_data")
        upload_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Get the BigQueryManager instance
        bq_manager = BigQueryManager(dataset_id=dataset_id)

        # Insert the workflow failure event into the BigQuery table
        bq_manager.insert_rows(
            table_id=workflow_failure_events_table_id,
            rows=[{
                "workflow_name": workflow_name,
                "failure_point": failure_point,
                "error_type": str(error_type),
                "error_message": str(error_message),
                "input_data": str(input_data),
                "upload_timestamp": upload_timestamp
            }]
        )


        return {"status": "success", 
                "log_message": "Workflow failure event logged successfully.",
                "logged_error_message": str(error_message)
            }

    except Exception as e:
        stack_trace = traceback.format_exc()
        log_error(
            function_name="handle_workflow_failure",
            endpoint="workflow-failure",
            log_message=str(e),
            error_type=type(e).__name__,
            stack_trace=stack_trace,
        )
        return {
            "status": "failed",
            "log_message": str(e),
            "error_type": type(e).__name__,
            "stack_trace": stack_trace,
        }

