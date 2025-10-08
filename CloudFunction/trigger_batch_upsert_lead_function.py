import functions_framework

from google.auth.transport.requests import Request
from google.oauth2 import service_account
import requests
from google.cloud import secretmanager
from requests.exceptions import ReadTimeout, RequestException
from google.cloud import workflows_v1
from google.cloud.workflows.executions_v1 import ExecutionsClient
from google.cloud.workflows.executions_v1.types import ListExecutionsRequest
from google.cloud import tasks_v2
from logging_config import log_default, log_error
import traceback

import time
import json
from config import get_settings
from utils.common import truncate_iso_to_seconds, invoke_cloud_function
from services import GCSFileManager

settings = get_settings()



client = ExecutionsClient()
tasks_client = tasks_v2.CloudTasksClient()
gcs_client = GCSFileManager(settings.GCS_BUCKET)

# Function to list active workflows
def list_active_workflows(parent):
    request = ListExecutionsRequest(
        parent=parent,
        filter='state="ACTIVE"',
    )
    response = client.list_executions(request=request)
    return [exec for exec in response.executions if exec.state.name == "ACTIVE"]

# Function to check for tasks in Cloud Tasks queues
def check_task_queues(
    queues : list,
    instance_cnt,
    FILE_PATH,
    timeCreated,
    check_task_ls
):
    
    for queue_name in queues:
        parent_queue = tasks_client.queue_path(settings.PROJECT_ID, settings.CLOUD_TASK_LOCATION, queue_name)
        request = tasks_v2.ListTasksRequest(
            parent=parent_queue,
        )
        tasks = []
        while True:
            response = tasks_client.list_tasks(request=request)

            for task in response.tasks:
                tasks.append(task.name)
            # Check for next page
            if response.next_page_token:
                request.page_token = response.next_page_token
            else:
                break
        # tasks = list(tasks_client.list_tasks(parent=parent_queue))
        if tasks:
            # Checking for specific tasks in queue
            if check_task_ls:
                # Checking provided  check_task_ls present in the  task queue
                common_elements = set(check_task_ls) & set(tasks)
                if common_elements:
                    return True
                else:
                    continue  # No relevant tasks found, continue to next queue
            else:
                # If no specific tasks are provided, return True if any tasks are found            
                # Log the number of tasks found in the queue
                log_default(
                    log_message=f"Instance {instance_cnt}:Tasks found in queue '{queue_name}': {len(tasks)}",
                    json_payload=json.dumps(
                        {   
                            "file_path": FILE_PATH,
                            "time_created": timeCreated,
                        }
                    ),
                )
                
                return True  # If any tasks are found, return True
            
    return False  # No tasks in any queue

# # Function to check timeout limits
def check_timeout(
        start_time,
        timeout_limit,
        instance_cnt,
        FILE_PATH,
        payload,
        timeCreated
):
    # Check if the current function execution time exceeds the timeout limit
    if time.time() - start_time > timeout_limit:
        log_default(
            log_message=f"Instance {instance_cnt}:Timeout reached, triggering another function and returning.",
            json_payload=json.dumps(
                {
                    "file_path": FILE_PATH,
                    "time_created": timeCreated,
                }
            ),
        )
        payload["event"]["instance_cnt"] = instance_cnt+1
        invoke_cloud_function(settings.TRIGGER_BATCH_UPSERT_CLOUD_FUNCTION_URL,payload=payload)
        return True
    return False

@functions_framework.http
def trigger_batch_upsert_lead(request):

    request_json = request.get_json(silent=True)
    if request_json:
        event = request_json.get("event", "No event provided")
    else:
        log_error(
            function_name="batch_upsert_leads",
            endpoint="batch-upsert-leads",
            log_message="No JSON payload received.",
        )
        return {
            "status": "failed",
            "log_message": "No JSON payload received.",
        }
    

    max_attempts = 3
    base_delay = 10  # seconds

    # Retry mechanism: try up to max_attempts with exponential backoff on failure
    for attempt in range(1, max_attempts + 1):
        try:

            FILE_PATH = event["name"]
            timeCreated = truncate_iso_to_seconds(event["timeCreated"])
            workflow_name = event["workflow_name"]
            backfill = event.get("backfill",False)
            search_ids = event.get("search_ids",None)
            bucket = event.get("bucket")
            batch_id = event["batch_id"]
            instance_cnt = event.get("instance_cnt", 1)



            start_time = time.time()  # Track the function execution time
            timeout_limit = 2700  # 45 minutes in seconds
            wait_time = 300  # 5 minutes in seconds
            check_interval = 120  # 2 minutes in seconds
            consecutive_checks = 3  # Number of consecutive checks for inactive workflows

            # Deciding for which workflow checking cloud task and workflow execution.
            if workflow_name == settings.WORKFLOW_INVOCATION_NAME:
                parent = client.workflow_path(settings.PROJECT_ID, settings.WORKFLOW_INVOCATION_LOCATION, settings.WORKFLOW_INVOCATION_NAME)
                queues = [settings.CLOUD_TASK_ASSIGN_SEARCH_QUEUE,
                            settings.CLOUD_TASK_SEND_PROJECT_TO_QUEUE_QUEUE,
                            settings.CLOUD_TASK_REROUTE_TO_SEARCH_OR_RELEVANCE_QUEUE] 
                cloud_function_name = settings.BATCH_UPSERT_LEADS_CLOUD_FUNCTION_URL
                task_ls = None
                trigger_payload = {
                    "event": {
                        "name": FILE_PATH,
                        "timeCreated": timeCreated,
                        "backfill": backfill ,
                        "search_ids" : search_ids,
                        "batch_id": batch_id
                    }
                }

            elif workflow_name == settings.WORKFLOW_DEDUPLICATION_RESOLUTION_NAME:
                parent = client.workflow_path(settings.PROJECT_ID, settings.WORKFLOW_INVOCATION_LOCATION, settings.WORKFLOW_DEDUPLICATION_RESOLUTION_NAME)
                queues = [  settings.CLOUD_TASK_SEND_PROJECT_TO_QUEUE_QUEUE  ] 
                cloud_function_name = settings.UNIFICATION_CLOUD_FUNCTION_URL
                # Getting task list created by deduplication process.It will check only those task created by deduplication process
                path = f"cloud_task/{FILE_PATH}_deduplicate_projects_task.json"
                task_ls=gcs_client.download_file(path,"json")["tasks"]
                trigger_payload = {
                    "event": {
                        "name": FILE_PATH,
                        "timeCreated": timeCreated,
                        "bucket": bucket,
                        "batch_id": batch_id
                        
                    }
                }
                
            else:
                raise Exception("Unknown Workflow name found.")


            
            

            # First check for active workflows
            active_executions = list_active_workflows(parent=parent)
            log_default(
                log_message=f"Instance {instance_cnt}:Running workflow instances: {len(active_executions)}",
                json_payload=json.dumps(
                    {
                        "file_path": FILE_PATH,
                        "time_created": timeCreated,
                    }
                ),
            )


            # Wait if there are active workflows and task in "cloud task queues"
            while len(active_executions) > 0 or check_task_queues(queues,instance_cnt,FILE_PATH,timeCreated,task_ls):
                log_default(
                    log_message=f"Instance {instance_cnt}:Waiting for active workflows and tasks to finish...",
                    json_payload=json.dumps(
                        {
                            "file_path": FILE_PATH,
                            "time_created": timeCreated,
                            "workflow_name": workflow_name,
                        }
                    ),
                )

                time.sleep(wait_time)  # Wait for 5 minutes
                active_executions = list_active_workflows(parent)
                log_default(
                    log_message=f"Instance {instance_cnt}:Running workflow instances: {len(active_executions)}",
                    json_payload=json.dumps(
                        {
                            "file_path": FILE_PATH,
                            "time_created": timeCreated,
                            "workflow_name": workflow_name,
                        }
                    ),
                )
            
                
                # Check if there are tasks in the queues
                if check_task_queues(
                    queues=queues,
                    instance_cnt=instance_cnt,
                    FILE_PATH=FILE_PATH,
                    timeCreated=timeCreated,
                    check_task_ls=task_ls
                ):
                    log_default(
                        log_message=f"Instance {instance_cnt}:Tasks found in one of the queues",
                        json_payload=json.dumps(
                            {
                                "file_path": FILE_PATH,
                                "time_created": timeCreated,
                                "workflow_name": workflow_name
                            }
                        ),
                    )

                if check_timeout(
                    start_time=start_time,
                    timeout_limit=timeout_limit,
                    instance_cnt=instance_cnt,
                    FILE_PATH=FILE_PATH,
                    payload={"event": event},
                    timeCreated=timeCreated
                ):
                    return "Timeout reached, function triggered again."

            # If no active workflows are found, try for 2-3 attempts with 2-minute gaps
            retries = 0
            while retries < consecutive_checks:
                log_default(
                    log_message=f"Instance {instance_cnt}:Retrying check {retries + 1}/{consecutive_checks} for inactive workflows and tasks...",
                    json_payload=json.dumps(
                        {
                            "file_path": FILE_PATH,
                            "time_created": timeCreated,
                            "workflow_name": workflow_name
                        }
                    ),
                )
                time.sleep(check_interval)  # Wait for 2 minutes between retries
                active_executions = list_active_workflows(parent=parent)
                
                # Check if there are tasks in the queues
                if check_task_queues(
                    queues=queues,
                    instance_cnt=instance_cnt,
                    FILE_PATH=FILE_PATH,
                    timeCreated=timeCreated,
                    check_task_ls=task_ls
                ):
                    log_default(
                        log_message=f"Instance {instance_cnt}:Tasks found in one of the queues",
                        json_payload=json.dumps(
                            {
                                "file_path": FILE_PATH,
                                "time_created": timeCreated,
                                "workflow_name": workflow_name,
                            }
                        ),
                    )
                    retries = 0  # Reset if tasks are found

                if len(active_executions) == 0 and not check_task_queues(queues,instance_cnt,FILE_PATH,timeCreated,task_ls):
                    retries += 1
                else:
                    retries = 0  # Reset if workflows or tasks are found
                log_default(
                    log_message=f"Instance {instance_cnt}:Running workflow instances: {len(active_executions)}",
                    json_payload=json.dumps(
                        {
                            "file_path": FILE_PATH,
                            "time_created": timeCreated,
                            "workflow_name": workflow_name,
                        }
                    ),
                )
                
                if check_timeout(
                    start_time=start_time,
                    timeout_limit=timeout_limit,
                    instance_cnt=instance_cnt,
                    FILE_PATH=FILE_PATH,
                    payload={"event": event},
                    timeCreated=timeCreated):
                    return "Timeout reached, function triggered again."

            log_default(
                log_message=f"Instance {instance_cnt}:No active workflows or tasks detected after retries.",
                json_payload=json.dumps(
                    {
                        "file_path": FILE_PATH,
                        "time_created": timeCreated,
                        "workflow_name": workflow_name,
                    }
                ),
            )
            
            # invoking batch_upsert_leads/unification cloud function.

            invoke_cloud_function(cloud_function_name,payload=trigger_payload)
            log_default(
                log_message=f"Instance {instance_cnt}:Triggered {cloud_function_name}.",
                json_payload=json.dumps(
                    {
                        "file_path": FILE_PATH,
                        "time_created": timeCreated,
                        "workflow_name": workflow_name,
                    }
                ),
            )
            # If task list logged by dedulplication process, then delete the task file from cloud storage.
            gcs_client.delete_file(f"cloud_task/{FILE_PATH}_deduplicate_projects_task.json")
            
            return f"Triggered {cloud_function_name} due to no active workflows and tasks."
        
        except Exception as e:

            if attempt == max_attempts:
                stack_trace = traceback.format_exc()
                log_error(
                    function_name="batch_upsert_leads",
                    endpoint="batch-upsert-leads",
                    log_message=str(e),
                    error_type=type(e).__name__,
                    stack_trace=stack_trace,
                    json_payload=json.dumps(
                            {"filenme": FILE_PATH
                                ,"time_created": timeCreated}
                    )
                )
                payload = {
                    "event":{
                        "workflow_name":"cloud_function:trigger_batch_upsert_lead",
                        "failure_point":"trigger_batch_upsert_lead",
                        "error_type":type(e).__name__,
                        "error_message":str(e),
                        "input_data":event
                    }
                }
                invoke_cloud_function(settings.WORKFLOW_FAILURE_CLOUD_FUNCTION_URL,payload=payload)
                return {
                    "status": "failed",
                    "log_message": str(e),
                    "error_type": type(e).__name__,
                    "stack_trace": stack_trace,
                    "file_path": FILE_PATH,
                    "time_created": timeCreated,
                }
            delay = base_delay ** attempt
            time.sleep(delay)