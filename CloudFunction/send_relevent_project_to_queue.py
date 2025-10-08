import concurrent.futures
import json
import traceback
from datetime import datetime

import functions_framework
import requests
from config import get_settings
from google.auth.transport.requests import Request
from google.cloud import secretmanager, bigquery
from google.oauth2 import service_account
from logging_config import log_default, log_error
from requests.exceptions import ReadTimeout, RequestException

from utils.common import get_secret, truncate_iso_to_seconds
from services import BigQueryManager, GCPCloudTaskClient
from tqdm import tqdm
from utils import (
    PROJECT_CANDIDATES_QUERY,
    DODGE_PROJECT_CANDIDATES_QUERY,
    find_nearby_branch_haversine,
    get_non_related_project_searches,
    get_processed_projects,
    should_process_project,
)

settings = get_settings()






@functions_framework.http
def send_projects_to_queue(request):

    try:

        request_json = request.get_json(silent=True)
        if request_json:
            event = request_json.get("event", "No event provided")
        else:
            log_error(
                function_name="send_projects_to_queue",
                endpoint="send-relevent-project-to-queue",
                log_message="No JSON payload received.",
            )
            return {
                "status": "failed",
                "log_message": "No JSON payload received.",
            }

        FILE_PATH = event["name"]
        TIME_CREATED = truncate_iso_to_seconds(event["timeCreated"])
        bucket = event.get("bucket")


        PROJECTS_FOR_DEDUPLICATION_TABLE_ID = settings.PROJECTS_FOR_DEDUPLICATION_TABLE_ID

        # Decide how to set force_process, e.g., from request or keep False
        force_process_flag = event.get("force_process", False)
        print("force_process_flag", force_process_flag)

        log_default(
            log_message="send_projects_to_queue function started......",
            json_payload=json.dumps(
                {
                    "filename": FILE_PATH,
                    "time_created": TIME_CREATED,
                }
            ),
        )

        
        if bucket == settings.GCS_SOURCE_BUCKET:
            project_candidates_query = PROJECT_CANDIDATES_QUERY.format(
                project=settings.PROJECT_ID,
                dataset=settings.BIGQUERY_DATASET,
                cc_table=settings.CC_FEED_TABLE_ID,
                relevant_categories_table=settings.RELEVANT_CATEGORIES_TABLE_ID,
                relevant_materials_table=settings.RELEVANT_MATERIALS_TABLE_ID,
                sourceFile=FILE_PATH,
                source_file_time_created=TIME_CREATED,
                sourceFilefilter = ''
            )
        elif bucket == settings.DODGE_GCS_SOURCE_BUCKET:
            project_candidates_query = DODGE_PROJECT_CANDIDATES_QUERY.format(
                project = settings.PROJECT_ID,
                dataset=settings.BIGQUERY_DATASET,
                dd_table=settings.DODGE_FEED_TABLE_ID,
                sourceFile=FILE_PATH,
                source_file_time_created=TIME_CREATED,
                sourceFilefilter = ''
            )
        else:
            log_error(
                function_name="send_projects_to_queue",
                endpoint="send-relevent-project-to-queue",
                log_message=f"Unsupported bucket: {bucket}. Expected {settings.GCS_SOURCE_BUCKET} or {settings.DODGE_GCS_SOURCE_BUCKET}"

            )
            return {
                "status": "failed",
                "log_message": f"Unsupported bucket: {bucket}. Expected {settings.GCS_SOURCE_BUCKET} or {settings.DODGE_GCS_SOURCE_BUCKET}",
                "error_type": "value_error"
            }

        
        bq_client = BigQueryManager(settings.BIGQUERY_DATASET)

        log_default(
            log_message="Fetching relevant project candidates from BigQuery...",
            json_payload=json.dumps(
                {"filename": FILE_PATH, "time_created": TIME_CREATED}
            ),
        )

        project_candidates_ls = bq_client.query_table(
            project_candidates_query, to_dataframe=True
        )

        batch_id = project_candidates_ls["batch_id"].loc[0] if not project_candidates_ls.empty else None

        job_config = bigquery.LoadJobConfig(
            write_disposition = "WRITE_APPEND",
            schema_update_options = [bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION],
            column_name_character_map = 'V2'
        )
        
        log_default(
            log_message="Loading project candidates to projects_for_deduplication table...",
            json_payload=json.dumps(
                {
                    "filename": FILE_PATH,
                    "time_created": TIME_CREATED,
                    "batch_id": batch_id,
                    "bucket": bucket
                }
            )
        )
        bq_client.load_from_dataframe(
            table_id=PROJECTS_FOR_DEDUPLICATION_TABLE_ID,
            dataframe=project_candidates_ls,
            job_config=job_config
        )
        

        return {
            "status": "success",
            "log_message": "send_projects_to_queue completed successfully",
            "filename": FILE_PATH,
            "time_created": TIME_CREATED,
            "batch_id": batch_id
        }

    except Exception as e:
        stack_trace = traceback.format_exc()
        log_error(
            function_name="send_projects_to_queue",
            endpoint="send-relevent-project-to-queue",
            log_message=str(e),
            error_type=type(e).__name__,
            stack_trace=stack_trace,
            json_payload=json.dumps(
                {
                    "filename": FILE_PATH,
                    "time_created": TIME_CREATED,
                }
            ),
        )
        return {
            "status": "failed",
            "log_message": str(e),
            "error_type": type(e).__name__,
            "stack_trace": stack_trace,
            "filename": FILE_PATH,
            "time_created": TIME_CREATED
        }
