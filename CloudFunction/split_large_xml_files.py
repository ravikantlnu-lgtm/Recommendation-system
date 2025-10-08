import functions_framework
import os
import re
from datetime import datetime
from io import BytesIO
import traceback
import json
# from google.cloud import bigquery, storage
from config import get_settings
from services import BigQueryManager, GCSFileManager
from logging_config import log_default, log_error
from utils.split_large_xml_files_utils import (
    delete_folder,
    download_gcs_file,
    insert_log,
    process_files_in_batches,
    split_large_xml,
)
from utils.common import truncate_iso_to_seconds

settings = get_settings()
big_query_client = BigQueryManager(dataset_id=settings.BIGQUERY_DATASET)
source_gcs_client = GCSFileManager(bucket=settings.GCS_SOURCE_BUCKET)
gcs_client = GCSFileManager(bucket=settings.GCS_BUCKET)

@functions_framework.http
def split_xml(request):
    try:
        request_json = request.get_json(silent=True)
        if request_json:
            event = request_json.get("event", "No event provided")
        else:
            event = "No JSON payload received"
            return "Error: event not recived."

        FILE_PATH = event["name"]
        timeCreated = truncate_iso_to_seconds(event["timeCreated"])

        SOURCE_BUCKET = settings.GCS_SOURCE_BUCKET
        PROJECT_ID = settings.PROJECT_ID
        BUCKET = settings.GCS_BUCKET
        DATASET = settings.BIGQUERY_DATASET
        LOG_TABLE = settings.HIST_DATALOAD_TABLE_ID
        CLOUD_FUNCTION_URL = settings.DATA_INTAKE_CLOUD_FUNCTION_URL
    
        # Determine the appropriate Cloud Function URL based on the file type.
        if event.get("historical_file"): 
            CLOUD_FUNCTION_URL = settings.HIST_XML_LOAD_CLOUD_FUNCTION_URL
        
        
        query = f"""
                SELECT count(*) cnt
                FROM `{settings.BIGQUERY_DATASET}.{settings.CC_FEED_TABLE_ID}`
                WHERE sourceFile = '{FILE_PATH}'
                AND sourceFileCreationTime = '{truncate_iso_to_seconds(timeCreated)}'
            """

        result = big_query_client.query_table(query=query)
        # Check if file already loaded or not.
        if result[0]["cnt"] > 0:
            log_default(
            log_message=f"Skipping already processed file: {FILE_PATH}",
            json_payload=json.dumps({"filename": FILE_PATH, "time_created": timeCreated}),
            )
            return {
            "status": "success",
            "log_message": "File already processed.",
            "file_path": FILE_PATH,
            "time_created": timeCreated,
            }

    

        log_default(log_message="Downloading file...", 
                    json_payload=json.dumps({"filename": FILE_PATH, "time_created": timeCreated})
        )

        temp_xml_file = download_gcs_file(source_gcs_client, FILE_PATH)
        output_prefix = "split_project"

        log_default(log_message="Splitting large XML file...",
                    json_payload=json.dumps({"filename": FILE_PATH, "time_created": timeCreated})
        )
        splitted_file_ls = split_large_xml(
            temp_xml_file, output_prefix, gcs_client, batch_size=2000
        )
        
        log_default(log_message="File split successfully",
                    json_payload=json.dumps({"filename": FILE_PATH, "time_created": timeCreated})
        )
        output_rows = process_files_in_batches(
            big_query_client, settings, FILE_PATH, timeCreated, splitted_file_ls, CLOUD_FUNCTION_URL, 70
        )
        log_default(log_message="Processed large XML file.",
                    json_payload=json.dumps({"filename": FILE_PATH, "time_created": timeCreated})
        )
        # insert_log(DATASET, LOG_TABLE, FILE_PATH, output_rows, big_query_client)
        delete_folder(gcs_client, f"tmp/temp_file_{FILE_PATH.split('/')[-1]}")
        
        log_default(log_message="Deleted temporary files",
                    json_payload=json.dumps({"filename": FILE_PATH, "time_created": timeCreated})
        )

        return {
            "status": "success",
            "log_message": "Processed large XML file.",
            "output_rows": output_rows,
            "filename": FILE_PATH,
            "time_created": timeCreated,
        }

    except Exception as e:
        stack_trace = traceback.format_exc()
        log_error(
            function_name="split_xml",
            endpoint="split-large-xml-files",
            log_message=str(e),
            error_type=type(e).__name__,
            stack_trace=stack_trace,
            json_payload=json.dumps({"filename": FILE_PATH, "time_created": timeCreated})
        )
        return {
            "status": "failed",
            "log_message": str(e),
            "error_type": type(e).__name__,
            "stack_trace": stack_trace,
            "filename": FILE_PATH,
            "time_created": timeCreated,
        }
    

