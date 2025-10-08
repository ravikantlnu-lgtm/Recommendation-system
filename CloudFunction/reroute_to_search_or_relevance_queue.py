import json
import traceback

import functions_framework
import requests
from config import get_settings
from logging_config import log_default, log_error
from services import GCPCloudTaskClient


@functions_framework.http
def reroute_to_search_or_relevance_queue(request):
    try:
        request_json = request.get_json(silent=True)

        if request_json is None:
            log_error(
                function_name="reroute_to_search_or_relevance_queue",
                log_message="No JSON payload received.",
            )
            return {
                "status": "failed",
                "log_message": "No JSON payload received.",
            }

        settings = get_settings()

        # Create a Cloud Task client
        task_client = GCPCloudTaskClient(
            project=settings.PROJECT_ID,
            location=settings.CLOUD_TASK_LOCATION,
            queue=settings.CLOUD_TASK_REROUTE_TO_SEARCH_OR_RELEVANCE_QUEUE,
            service_account_email=settings.WORKFLOW_INVOCATION_SA,
        )

        WORKFLOW_INVOCATION_URL = f"https://workflowexecutions.googleapis.com/v1/projects/{settings.PROJECT_ID}/locations/{settings.WORKFLOW_INVOCATION_LOCATION}/workflows/{settings.WORKFLOW_INVOCATION_NAME}/executions"

        # Fetch the request_type (send_project_to_queue, assign_project_to_search) to pass to the workflow
        request_type = request_json["assign_queue"]

        # Add the queue name to the payload
        request_json["assign_queue"] = "send_project_to_search_or_relevance_queue"

        # Save the request_type to the payload
        request_json["request_type"] = request_type

        log_default(
            log_message="Reroute to search or relevance queue request received",
            json_payload=json.dumps(request_json),
        )

        # Pass playload straight to the workflow
        task_client.create_task(url=WORKFLOW_INVOCATION_URL, payload=request_json)

        return {
            "status": "success",
            "log_message": f"reroute_to_search_or_relevance_queue completed successfully",
            "payload": request_json,
        }

    except Exception as e:

        stack_trace = traceback.format_exc()
        log_error(
            function_name="reroute_to_search_or_relevance_queue",
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
