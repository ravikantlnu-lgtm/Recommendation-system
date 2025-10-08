import json
import traceback
import time
import pandas as pd

import functions_framework
from config import get_settings
from logging_config import log_default, log_error
from services import BigQueryManager, GCPCloudTaskClient
from utils.assign_project_to_search_utils import (
    insert_assigned_search,
    run_prompt_assign_project_search,
    calculate_materials_valuation,
)
from utils.common import get_search_boolean, fetch_project_data, get_ranking_columns

settings = get_settings()

big_query_client = BigQueryManager(dataset_id=settings.BIGQUERY_DATASET)

@functions_framework.http
def assign_project_search(request):
    """
    The entry point function for the HTTP request.
    Args:
        request (flask.Request): The request object.
    """
    query_project_id = None
    search_id = None
    max_retries = 3
    backoff = 5

    for attempt in range(max_retries):
        try:
            request_json = request.get_json()
            if request_json is None: 
                raise ValueError("Request JSON is None")
            
            query_project_id = request_json["project_id"]
            search_id = request_json["search_id"]
            project_territory_id = request_json["territory_id"]
            time_created = request_json["time_created"]
            search_materials_json = request_json["search_materials_json"]
            batch_id = request_json["batch_id"]

            log_default(
                log_message="Assign search request received",
                json_payload=json.dumps(
                    {
                        "project_id": query_project_id,
                        "search_id": search_id,
                        "territory_id": project_territory_id,
                        "time_created": time_created,
                        "search_materials_json": search_materials_json,
                    }
                ),
            )

            # Create a Cloud Task client
            task_client = GCPCloudTaskClient(
                project=settings.PROJECT_ID,
                location=settings.CLOUD_TASK_LOCATION,
                queue=settings.CLOUD_TASK_ASSIGN_SEARCH_QUEUE,
                service_account_email=settings.WORKFLOW_INVOCATION_SA,
            )

            WORKFLOW_INVOCATION_URL = f"https://workflowexecutions.googleapis.com/v1/projects/{settings.PROJECT_ID}/locations/{settings.WORKFLOW_INVOCATION_LOCATION}/workflows/{settings.WORKFLOW_INVOCATION_NAME}/executions"

            search_product_materials_df = pd.read_json(search_materials_json)

            result = process_project_search(
                query_project_id=query_project_id,
                query_search_id=search_id,
                project_territory_id=project_territory_id,
                search_product_materials_df=search_product_materials_df, 
                time_created=time_created,
            )

            # Check if the response contains an error type
            if isinstance(result, dict) and result.get("error_type"):
                error_type = result["error_type"]
                error_message = result.get("log_message", "Unknown error")
                
                log_default(
                    log_message=f"process_project_search returned error: {error_type} - {error_message} (Attempt {attempt + 1}/{max_retries})",
                    json_payload=json.dumps(request_json),
                )

                if error_type == "PROJECT_NOT_FOUND" or error_type == "SEARCH_NOT_FOUND": 
                    # Don't retry for data not found errors
                    return { 
                        "status": "failed", 
                        "log_message": error_message,
                        "error_type": error_type,
                        "project_id": query_project_id,
                        "search_id": search_id,
                        "territory_id": project_territory_id,
                    }
                else: 
                    # Retry for LLM errors and other transient errors
                    if attempt < max_retries - 1:
                        time.sleep(backoff * (2 ** attempt)) # Exponential backoff
                        continue 
                    
                    # If last attempt, return error
                    else: 
                        return { 
                            "status": "failed", 
                            "log_message": "process_project_search failed after all retries",
                            "error_type": error_type,
                            "project_id": query_project_id,
                            "search_id": search_id,
                            "territory_id": project_territory_id,
                        }

            # If no error, unpack the result and continue
            else: 
                materials_valuation, llm_response = result

                # Check if the project is related to the search
                project_search_result = {}
                project_search_result["reasoning"] = llm_response["Reasoning"]

                if llm_response["Project_related_to_Search"] == "YES":
                    for idx, territory in enumerate(project_territory_id):
                        project_search_result["project_id"] = query_project_id
                        project_search_result["search_id"] = search_id
                        project_search_result["territory_id"] = territory["territory_id"]
                        project_search_result["time_created"] = time_created
                        project_search_result["distance_from_territory"] = territory[
                            "distance_from_territory"
                        ]

                        project_search_result['search_materials_json'] = search_materials_json
                        project_search_result['materials_valuation'] = materials_valuation

                        project_search_result["assign_search"] = "false"
                        project_search_result["territory_idx"] = idx

                        project_search_result["assign_queue"] = "assign_project_to_search"
                        project_search_result["request_type"] = None
                        project_search_result["batch_id"] = batch_id

                        task_client.create_task(
                            url=WORKFLOW_INVOCATION_URL, payload=project_search_result
                        )

                    return {
                        "status": "success",
                        "log_message": "assign_project_search function completed",
                        "match": True,
                        "project_id": query_project_id,
                        "search_id": search_id,
                        "territory_id": project_territory_id,
                        "time_created": time_created,
                    }
                else:
                    # Add counter for completed projects
                    return {
                        "status": "success",
                        "log_message": "assign_project_search function completed",
                        "match": False,
                        **project_search_result,
                    }

        except Exception as e:
            stack_trace = traceback.format_exc()
            log_error(
                function_name="assign_search_cloud_function",
                endpoint="assign_search",
                log_message=str(e),
                error_type=type(e).__name__,
                stack_trace=stack_trace,
                json_payload=json.dumps(
                    {
                        "project_id": query_project_id,
                        "search_id": search_id,
                        "territory_id": project_territory_id,
                        "time_created": time_created,
                    }
                ),
            )
            #Add counter for completed projects
            return {
                "status": "failed",
                "log_message": str(e),
                "error_type": type(e).__name__,
                "stack_trace": stack_trace,
                "project_id": query_project_id,
            }


def process_project_search(
    query_project_id: str,
    query_search_id: str,
    project_territory_id: str,
    search_product_materials_df: pd.DataFrame,
    time_created: str,
) -> dict | tuple:
    """
    Process the project_id and search_id to  assign the project to the search.
    Args:
        query_project_id (str): The project_id.
        query_search_id (str): The search_id.
        project_territory_id (str): The project_territory_id.
        time_created (str): The time_created.
    Returns:
        dict: The JSON response received from the LLM prompt.
    """

    ranking_cols = get_ranking_columns(big_query_client)
    if ranking_cols is None:
        ranking_cols = []
    select_columns = ", ".join([f"`{col}`" for col in ranking_cols])
    
    # Fetch merged project data from ConstructConnect and Dodge
    project_data = fetch_project_data(big_query_client, query_project_id, select_columns)

    if project_data is None:
        log_default(
            log_message="Project not found",
            json_payload=json.dumps(
                {
                    "project_id": query_project_id,
                    "search_id": query_search_id,
                    "territory_id": project_territory_id,
                    "time_created": time_created,
                }
            ),
        )
        # Return PROJECT_NOT_FOUND error
        return { 
            "error_type": "PROJECT_NOT_FOUND",
            "log_message": "Project not found",
            "project_id": query_project_id,
            "search_id": query_search_id,
            "territory_id": project_territory_id,
        }

    project_json_data = json.loads(project_data)
    log_default(
        log_message="Project data retrieved",
        json_payload=json.dumps(
            {
                "project_id": query_project_id,
                "search_id": query_search_id,
                "territory_id": project_territory_id,
                "time_created": time_created,
                **project_json_data[0],
            }
        ),
    )

    # Get boolean search query from search_id
    boolean_search_result = get_search_boolean(
        query_search_id=query_search_id, big_query_client=big_query_client
    )
    if not boolean_search_result:
        log_default(
            log_message="Search not found",
            json_payload=json.dumps(
                {
                    "project_id": query_project_id,
                    "search_id": query_search_id,
                    "territory_id": project_territory_id,
                    "time_created": time_created,
                }
            ),
        )
        # Return SEARCH_NOT_FOUND error
        return { 
            "error_type": "SEARCH_NOT_FOUND",
            "log_message": "Search not found",
            "project_id": query_project_id,
            "search_id": query_search_id,
            "territory_id": project_territory_id,
        }

    boolean_search_json = json.loads(boolean_search_result)

    log_default(
        log_message="Boolean search details retrieved",
        json_payload=json.dumps(
            {
                "project_id": query_project_id,
                "search_id": query_search_id,
                "territory_id": project_territory_id,
                "time_created": time_created,
                **boolean_search_json[0],
            }
        ),
    )

    # Gemini prompt to find if the Search is related to the Project.
    output = run_prompt_assign_project_search(
        search_name=boolean_search_json[0]["name"],
        search_query=boolean_search_json[0]["boolean"],
        cc_project_json=project_json_data[0],
    )

    
    if output is None:
        log_default(
            log_message="LLM response is None",
            json_payload=json.dumps(
                {
                    "project_id": query_project_id,
                    "search_id": query_search_id,
                    "territory_id": project_territory_id,
                    "time_created": time_created,
                }
            ),
        )
        # Return LLM_ERROR
        return { 
            "error_type": "LLM_ERROR",
            "log_message": "LLM response is None",
            "project_id": query_project_id,
            "search_id": query_search_id,
            "territory_id": project_territory_id,
        }
    
    log_default(
        log_message="LLM prompt output received",
        json_payload=json.dumps(
            {
                "project_id": query_project_id,
                "search_id": query_search_id,
                "territory_id": project_territory_id,
                "time_created": time_created,
                **json.loads(output.model_dump_json()),
            }
        ),
    )

    json_output = json.loads(output.model_dump_json())
    log_default(
        log_message="LLM output parsed into JSON",
        json_payload=json.dumps(
            {
                "project_id": query_project_id,
                "search_id": query_search_id,
                "territory_id": project_territory_id,
                "time_created": time_created,
                **json_output,
            }
        ),
    )

    # Fetch decision from the LLM output
    project_related_to_search = json_output["Project_related_to_Search"]

    if project_related_to_search == "YES": 

        materials_valuation_dict = calculate_materials_valuation(project_data=project_json_data[0],
                                                                search_id=boolean_search_json[0]["id"],
                                                                search_product_materials_df=search_product_materials_df)
        materials_valuation = json.dumps(materials_valuation_dict)     

    else: 
        materials_valuation = "{}"
   
    # Insert the project-search pair in the assigned_search table with "YES" or "NO" in "is_related" column and material valuation
    insert_assigned_search(
        query_project_id=query_project_id,
        query_search_id=query_search_id,
        project_territory_id=project_territory_id,
        time_created=time_created,
        is_related=project_related_to_search,
        big_query_client=big_query_client,
        materials_valuation=materials_valuation,
    )

    return materials_valuation, json_output
