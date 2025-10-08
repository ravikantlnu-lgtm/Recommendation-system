
import json


import functions_framework
import pandas as pd
from collections import defaultdict
from google.cloud import bigquery

import traceback
from config import get_settings
from services import BigQueryManager, GCPCloudTaskClient
from logging_config import log_default, log_error
from utils.common import truncate_iso_to_seconds
from utils.unification_utils import (
    UnionFind, 
    get_uuid, 
    normalize_project,
    SEARCHES_QUERY,
    TERRITORIES_QUERY,
    DUPLICATE_PROJECTS_QUERY,
    POTENTIAL_MATCH_PROJECTS_QUERY,
    INSERT_SOURCE_LINKING_QUERY,
    INSERT_UNIQUE_PROJECTS_QUERY,
    UNIQUE_PROJECT_CANDIDATES_QUERY,
    CONSOLIDATED_PRIMARY_PROJECT_QUERY,
    COALESCED_PRIMARY_PROJECT_QUERY,
    EXISTING_PRIMARY_PROJECTID_QUERY

)
from utils.send_relevent_project_to_queue_utils import(
    find_nearby_branch_haversine,
    project_search_to_task_queue,
    invoke_cloud_function
)

# Match Status Constants
MATCH_STATUS_MATCH = 'match'
MATCH_STATUS_UNSURE = 'unsure'
MATCH_STATUS_NO_MATCH = 'no_match'

settings = get_settings()
big_query_client = BigQueryManager(dataset_id=settings.BIGQUERY_DATASET)

task_client = GCPCloudTaskClient(
            project=settings.PROJECT_ID,
            location=settings.CLOUD_TASK_LOCATION,
            queue=settings.CLOUD_TASK_SEND_PROJECT_TO_QUEUE_QUEUE,
            service_account_email=settings.WORKFLOW_INVOCATION_SA,
        )

def _execute_parameterized_query(query_template, query_params, to_dataframe =False, **table_format_args):
    """Helper to format and run a parameterized BQ query."""
    table_path = f"{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}"
    
    # Safely format table names into the query template
    formatted_query = query_template.format(
        table_path=f"{table_path}.{table_format_args.get('table_id')}",
        target_table_path=f"{table_path}.{table_format_args.get('target_table_id')}",
        source_table_path=f"{table_path}.{table_format_args.get('source_table_id')}",
        primary_lead_table_path=f"{table_path}.{settings.PRIMARY_PROJECT_LEAD_TABLE_ID}",
        cc_feed_table_path=f"{table_path}.{settings.CC_FEED_TABLE_ID}",
        dodge_feed_table_path=f"{table_path}.{settings.DODGE_FEED_TABLE_ID}",
        searches_table_path=f"{table_path}.{settings.SEARCHES_TABLE_ID}",
        search_territory_table_path=f"{table_path}.{settings.SEARCH_TERRITORY_TABLE_ID}",
        consolidated_primary_project_table_path = f"{table_path}.{settings.CONSOLIDATED_PRIMARY_PROJECT_LEAD_TABLE_ID}",
    )

    job_config = bigquery.QueryJobConfig(query_parameters=query_params)
    return big_query_client.query_table(query=formatted_query,to_dataframe=to_dataframe, job_config=job_config)

def _load_dataframe_to_bq(dataframe, table_id, log_context, schema = None):
    """Loads a Pandas DataFrame to a specified BigQuery table."""
    job_config = bigquery.LoadJobConfig(
        write_disposition="WRITE_APPEND",
        schema_update_options=[bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION],
        schema = schema
    )
    log_default(log_message=f"Loading DataFrame to {table_id}", json_payload=json.dumps(log_context))
    big_query_client.load_from_dataframe(
        table_id=table_id,
        dataframe=dataframe,
        job_config=job_config
    )


def process_duplicate_projects(batch_id, log_context):
    """Groups and loads 'match' status projects."""
    # Analyzing all pairs with a "Clear Match" or "Duplicate" status to find groups of interconnected projects.
    # Creating groups.
    log_default(log_message="Processing 'match' projects to form duplicate groups.", json_payload=json.dumps(log_context))
    
    query_params = [
        bigquery.ScalarQueryParameter("batch_id", "STRING", batch_id),
        bigquery.ScalarQueryParameter("match_status", "STRING", MATCH_STATUS_MATCH),
    ]
    duplicate_projects = _execute_parameterized_query(
        DUPLICATE_PROJECTS_QUERY, 
        query_params, 
        table_id=settings.LLM_DEDUPLICATION_RESULT_TABLE_ID
    )

    uf = UnionFind()
    id_to_data = {}
    for match in duplicate_projects:
        p = normalize_project(match["project"])
        m = normalize_project(match["potential_match_project"])
        uf.union(p["project_id"], m["project_id"])
        id_to_data[p["project_id"]] = p
        id_to_data[m["project_id"]] = m

    groups = defaultdict(list)
    for pid in id_to_data:
        root = uf.find(pid)
        groups[root].append(id_to_data[pid])
    grouped_data = []
    for members in groups.values():
        get_existing_primary = lambda members: next(
                (item["existing_primary_project_id"] for item in members if item.get("existing_primary_project_id")), 
                    None
                )
        existing_primary_project_id = get_existing_primary(members)
        if existing_primary_project_id:
            primary_project_id = existing_primary_project_id
        else:
            primary_project_id = get_uuid()

        for index, value in enumerate(members):
            del members[index]['existing_primary_project_id']
        grouped_data.append(
            {
                "primary_project_id": primary_project_id,
                "batch_id": batch_id,
                "match_status": MATCH_STATUS_MATCH,
                "matched_group": [
    {k: v for k, v in project.items() if k != "existing_primary_project_id"}
    for project in sorted(members, key=lambda x: x["project_id"])
]

            } )
    
    if grouped_data:
        df = pd.DataFrame(grouped_data)
        _load_dataframe_to_bq(df, settings.PRIMARY_PROJECT_LEAD_TABLE_ID, log_context)

def process_potential_match_projects(batch_id, log_context):
    """Groups and loads 'unsure' status projects."""
    # Analyzing the remaining pairs with an "Unsure" status to find "Unsure Groups."
    log_default(log_message="Processing 'unsure' projects to form potential match groups.", json_payload=json.dumps(log_context))

    query_params = [
        bigquery.ScalarQueryParameter("batch_id", "STRING", batch_id),
        bigquery.ScalarQueryParameter("match_status", "STRING", MATCH_STATUS_UNSURE),
    ]
    potential_matches = _execute_parameterized_query(
        POTENTIAL_MATCH_PROJECTS_QUERY, 
        query_params,
        table_id=settings.LLM_DEDUPLICATION_RESULT_TABLE_ID
    )

    groups = {}
    for match in potential_matches:
        project = normalize_project(match["project"])
        potential_match = normalize_project(match["potential_match_project"])

        if project['existing_primary_project_id']:
            primary_project_id = project['existing_primary_project_id']
        else:
            primary_project_id = get_uuid()
        
        if project["project_id"] not in groups:
            groups[project["project_id"]] = {
                "primary_project_id": primary_project_id,
                "batch_id": batch_id,
                "match_status": MATCH_STATUS_UNSURE,
                "matched_group": [project],
                "potential_duplicates": [],
            }
        groups[project["project_id"]]["potential_duplicates"].append(potential_match)

    if groups:
        df = pd.DataFrame(list(groups.values()))
        _load_dataframe_to_bq(df, settings.PRIMARY_PROJECT_LEAD_TABLE_ID, log_context)

def insert_linked_and_unique_projects(batch_id, log_context):
    """Inserts records into SOURCE_LINKING and adds unique projects to PRIMARY_PROJECT_LEAD."""
    log_default(log_message="Inserting matched/unsure records into SOURCE_LINKING.", json_payload=json.dumps(log_context))
    query_params = [
        bigquery.ScalarQueryParameter("batch_id", "STRING", batch_id),
        bigquery.ScalarQueryParameter("match", "STRING", MATCH_STATUS_MATCH),
        bigquery.ScalarQueryParameter("unsure", "STRING", MATCH_STATUS_UNSURE),
    ]
    _execute_parameterized_query(
        INSERT_SOURCE_LINKING_QUERY, 
        query_params,
        target_table_id=settings.SOURCE_LINKING_TABLE_ID,
        source_table_id=settings.PRIMARY_PROJECT_LEAD_TABLE_ID
    )

    log_default(log_message="Inserting unique ('no_match') records into PRIMARY_PROJECT_LEAD.", json_payload=json.dumps(log_context))
    query_params = [
        bigquery.ScalarQueryParameter("batch_id", "STRING", batch_id),
        bigquery.ScalarQueryParameter("no_match_status", "STRING", MATCH_STATUS_NO_MATCH),
    ]
    _execute_parameterized_query(
        INSERT_UNIQUE_PROJECTS_QUERY, 
        query_params,
        target_table_id=settings.PRIMARY_PROJECT_LEAD_TABLE_ID,
        source_table_id=settings.LLM_DEDUPLICATION_RESULT_TABLE_ID
    )

def process_and_queue_unique_projects(event_data, log_context):
    """Fetches unique projects, finds nearby branches, and sends them to a task queue."""
    log_default(log_message="Fetching and processing unique projects for queuing.", json_payload=json.dumps(log_context))
    
    query_params = [
        bigquery.ScalarQueryParameter("batch_id", "STRING", event_data["batch_id"]),
        bigquery.ScalarQueryParameter("delta", "BOOL", True),
    ]
    project_candidates_df = _execute_parameterized_query(
        UNIQUE_PROJECT_CANDIDATES_QUERY, 
        query_params,
        to_dataframe=True
    )

    if project_candidates_df.empty:
        log_default(log_message="No unique projects to process.", json_payload=json.dumps(log_context))
        return

    territories_df = big_query_client.query_table(
        TERRITORIES_QUERY.format(table_path=f"{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.{settings.TERRITORIES_TABLE_ID}"),
        to_dataframe=True
    )
    
    searches_ls = big_query_client.query_table(
        SEARCHES_QUERY.format(
            searches_table_path=f"{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.{settings.SEARCHES_TABLE_ID}",
            search_territory_table_path=f"{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.{settings.SEARCH_TERRITORY_TABLE_ID}"
        )
    )

    project_candidates_df["assigned_branches"] = project_candidates_df.apply(
        lambda row: find_nearby_branch_haversine(
            row=row,
            df_branch=territories_df,
            radius_miles=settings.RADIUS_MILES,
            max_branches=settings.MAX_BRANCHES,
        ),
        axis=1,
    )

    log_default(
        log_message="Fetching search-product-materials mappings from BigQuery...", 
        json_payload=json.dumps(log_context),
    )

    # Get search-materials mappings 
    search_product_category_query = f"""select sp.fbm_searchid, sp.fbm_productcategoryid, pm.material, pm.code 
                                        from `{settings.BIGQUERY_DATASET}.{settings.SEARCH_PRODUCT_CATEGORY_MAP_TABLE_ID}` sp 
                                        left join `{settings.BIGQUERY_DATASET}.{settings.PRODUCT_CATEGORY_MATERIALS_MAP_TABLE_ID}` pm 
                                        on sp.fbm_productcatcode=pm.fbm_productcatcode"""
    search_product_materials_df = big_query_client.query_table(search_product_category_query, to_dataframe=True)

    log_default(log_message="Sending unique projects to task queue.", json_payload=json.dumps(log_context))
    workflow_url = f"https://workflowexecutions.googleapis.com/v1/projects/{settings.PROJECT_ID}/locations/{settings.WORKFLOW_INVOCATION_LOCATION}/workflows/{settings.WORKFLOW_INVOCATION_NAME}/executions"
    
    project_search_to_task_queue(
        project_candidates_df,
        searches_ls,
        search_product_materials_df,
        task_client,
        workflow_url,
        big_query_client,
        settings,
        FILE_PATH=event_data["name"],
        TIME_CREATED=event_data["timeCreated"],
        bucket=event_data["bucket"],
        batch_id=event_data["batch_id"],
        force_process=event_data.get("force_process", False),
    )

def insert_consolidated_primary_project_leads(batch_id, log_context):
    """Inserts records into consolidated_primary_project_leads."""
    log_default(log_message="Inserting  records into consolidated_primary_project_leads.", json_payload=json.dumps(log_context))
    query_params = [
        bigquery.ScalarQueryParameter("batch_id", "STRING", batch_id)
    ]
    consolidated_df = _execute_parameterized_query(
        CONSOLIDATED_PRIMARY_PROJECT_QUERY, 
        query_params,
        to_dataframe=True
    )

    if not consolidated_df.empty:
        schema =  big_query_client.get_schema(settings.CONSOLIDATED_PRIMARY_PROJECT_LEAD_TABLE_ID) 
        _load_dataframe_to_bq(consolidated_df, settings.CONSOLIDATED_PRIMARY_PROJECT_LEAD_TABLE_ID, log_context, schema)

    log_default(log_message="Inserting records into COALESCED_PRIMARY_PROJECT table.", json_payload=json.dumps(log_context))
    query_params = [
        bigquery.ScalarQueryParameter("batch_id", "STRING", batch_id),
    ]
    coalesced_df = _execute_parameterized_query(
        COALESCED_PRIMARY_PROJECT_QUERY, 
        query_params,
        to_dataframe=True
    )

    if not coalesced_df.empty:
        schema =  big_query_client.get_schema(settings.COALESCED_PRIMARY_PROJECT_TABLE_ID) 
        schema = [field for field in schema if field.name.lower() != "insert_timestamp".lower()]
        _load_dataframe_to_bq(coalesced_df, settings.COALESCED_PRIMARY_PROJECT_TABLE_ID, log_context, schema)

def assign_existing_primary_project_id(batch_id, log_context):
    "Assgin already existing for project project_id in llm table"
    query_params = [
        bigquery.ScalarQueryParameter("batch_id", "STRING", batch_id)
    ]
    
    _execute_parameterized_query(
        EXISTING_PRIMARY_PROJECTID_QUERY, 
        query_params,
        target_table_id=settings.LLM_DEDUPLICATION_RESULT_TABLE_ID,
        source_table_id=settings.PRIMARY_PROJECT_LEAD_TABLE_ID
    )

        

@functions_framework.http
def unification(request):
    """HTTP Cloud Function.
    Args:
        request (flask.Request): The request object.
        <https://flask.palletsprojects.com/en/1.1.x/api/#incoming-request-data>
    Returns:
        The response text, or any set of values that can be turned into a
        Response object using `make_response`
        <https://flask.palletsprojects.com/en/1.1.x/api/#flask.make_response>.
    """
    try:
        request_json = request.get_json(silent=True)
        if not request_json or "event" not in request_json:
            log_error(function_name="unification", endpoint="unification", log_message="Invalid JSON payload received.")
            return {"status": "failed", "log_message": "Invalid JSON payload received."}
        
        
        event = request_json["event"]
        bucket = event.get("bucket")
        batch_id = event["batch_id"]
        force_process_flag = event.get("force_process", False)
        print("force_process_flag", force_process_flag)

        log_context = {
            "filename": event["name"],
            "time_created": truncate_iso_to_seconds(event["timeCreated"]),
            "batch_id": batch_id
        }
        
        assign_existing_primary_project_id(batch_id, log_context)
        # Step 1: Process and group 'match' (duplicate) projects
        process_duplicate_projects(batch_id, log_context)

        # Step 2: Process and group 'unsure' (potential match) projects
        process_potential_match_projects(batch_id, log_context)

        # Step 3: Insert linked sources and unique projects using efficient BQ queries
        insert_linked_and_unique_projects(batch_id, log_context)

        # Step 4: insert consolidated_primary_project_leads
        insert_consolidated_primary_project_leads(batch_id, log_context)

        # Step 5: Process the now-unique projects and send to task queue
        process_and_queue_unique_projects(event, log_context)
        
        # Step 6: Trigger downstream workflow
        log_default(log_message="Triggering batch upsert workflow.", json_payload=json.dumps(log_context))      
        
        payload = {
            "event": {
                "name": event.get('name'),
                "timeCreated": event.get('timeCreated'),
                "workflow_name": settings.WORKFLOW_INVOCATION_NAME,
                "batch_id": batch_id,
            }
        }

        invoke_cloud_function(settings.TRIGGER_BATCH_UPSERT_CLOUD_FUNCTION_URL, payload)

        return {
            "status": "success",
            "log_message": "Unification process completed successfully.",
            "filename": event.get('name'),
            "time_created": event.get('timeCreated'),
            "bucket": event.get("bucket"),
            "batch_id": event.get("batch_id"),
        }


    except Exception as e:
        stack_trace = traceback.format_exc()
        log_error(
            function_name="unification",
            endpoint="unification",
            log_message=str(e),
            error_type=type(e).__name__,
            stack_trace=stack_trace,
            json_payload=json.dumps(
                {
                    "filename": event.get('name'),
                    "time_created": event.get('timeCreated'),
                    "bucket": event.get("bucket"),
                    "batch_id": event.get("batch_id")

                }
            ),
        )
        return {
            "status": "failed",
            "log_message": str(e),
            "error_type": type(e).__name__,
            "stack_trace": stack_trace,
            "filename": event.get('name'),
            "time_created": event.get('timeCreated'),
            "bucket": event.get("bucket"),
            "batch_id": event.get("batch_id")
        }
         
