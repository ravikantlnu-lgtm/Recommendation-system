import base64
import json
import os
import xml.etree.ElementTree as ET
from decimal import Decimal

import functions_framework
import pandas as pd
import xmlschema
import traceback
from config import get_settings
from services import BigQueryManager, GCSFileManager
from logging_config import log_default, log_error
from utils.data_intake_utils import ack_receipt, process_file, push_to_bq
from utils.common import get_uuid, truncate_iso_to_seconds


settings = get_settings()
big_query_client = BigQueryManager(dataset_id=settings.BIGQUERY_DATASET)


@functions_framework.http
def gcs_to_bq(request):
    """HTTP Cloud Function.
    Args:
        request (flask.Request): The request object.
        <https://flask.palletsprojects.com/en/1.1.x/api/#incoming-request-data>
    Returns:
        The response text, or any set of values that can be turned into a
        Response object using `make_response`
        <https://flask.palletsprojects.com/en/1.1.x/api/#flask.make_response>.
    """
    request_json = request.get_json(silent=True)
    if request_json:
        event = request_json.get("event", "No event provided")
    else:
        log_error(
            function_name="gcs_to_bq",
            endpoint="process-xml-files",
            log_message="No JSON payload received.",
        )
        return {
            "status": "failed",
            "log_message": "No JSON payload received.",
        }

    FILE_PATH = event["name"]
    timeCreated = truncate_iso_to_seconds(event["timeCreated"])
    bucket = event.get("bucket")

    if bucket == settings.GCS_SOURCE_BUCKET or bucket == settings.GCS_BUCKET: 
        TABLE_ID = settings.CC_FEED_TABLE_ID
    elif bucket == settings.DODGE_GCS_SOURCE_BUCKET:
        TABLE_ID =  settings.DODGE_FEED_TABLE_ID
    else:
        raise Exception(f"Unknown source bucket: {bucket}")
    

    ack_receipt()

    gcs_client = GCSFileManager(bucket)
   
    if not FILE_PATH.split("/")[-1]:
        log_default(log_message=f"Skipping empty file path: {FILE_PATH}",
                    json_payload=json.dumps(
                            {"filenme": FILE_PATH ,"time_created": timeCreated, "bucket": bucket}
                    )
        )

        return {
            "status": "failed",
            "log_message": f"It's a folder, skipping: {FILE_PATH}",
        }


    if not FILE_PATH.endswith(".xml"):
        log_default(log_message=f"Skipping non-XML file: {FILE_PATH}",
                    json_payload=json.dumps(
                            {"filenme": FILE_PATH,"time_created": timeCreated, "bucket": bucket}
                    )
        )
        return {
            "status": "failed",
            "log_message": f"Skipping non-XML file: {FILE_PATH}",
        }

    try:
        # If the splitted files come, it will check in split_large_xml_files cloud function if the file is loaded or not; otherwise, it will check here.
        if not event.get("splitted"):
            query = f"""
                SELECT count(*) cnt
                FROM `{settings.BIGQUERY_DATASET}.{TABLE_ID}`
                WHERE sourceFileCreationTime = '{truncate_iso_to_seconds(timeCreated)}' 
                AND sourceFile = '{FILE_PATH}'
            """

            result = big_query_client.query_table(query=query)

            if result[0]["cnt"] > 0:
                log_default(
                log_message=f"Skipping already processed file: {FILE_PATH}",
                json_payload=json.dumps({"filename": FILE_PATH, "time_created": timeCreated, "bucket": bucket}),
                )
                
                return {
                "status": "success",
                "log_message": "File already processed.",
                "file_path": FILE_PATH,
                "time_created": timeCreated,
                }
        
        
        log_default(log_message="Processing the XML file...",
                    json_payload=json.dumps(
                            {"filenme": FILE_PATH,"time_created": timeCreated, "bucket": bucket}
                    )
        )
        df = process_file(FILE_PATH, gcs_client, bucket, settings)
        log_default(log_message=f"{FILE_PATH} XML file processed",
                    json_payload=json.dumps(
                            {"filenme": FILE_PATH,"time_created": timeCreated, "bucket": bucket}
                    )
        )
        if "splitted" in event.keys() and "source_filepath" in event.keys():
            df["sourceFile"] = event["source_filepath"]
        else:
            df["sourceFile"] = FILE_PATH
        df["sourceFileCreationTime"] = str(timeCreated)
        df['sourceFileCreationTime'] = pd.to_datetime(df['sourceFileCreationTime'])
        df['sourceFileCreationTime'] =df['sourceFileCreationTime'].dt.floor('s')
        if df is not None:
            
            log_default(log_message=f"Pushing {FILE_PATH} records to BQ.",
                        json_payload=json.dumps(
                                {"filenme": FILE_PATH,"time_created": timeCreated, "bucket": bucket}
                        )
            )
            push_to_bq(df, big_query_client, TABLE_ID ,FILE_PATH)
            log_default(log_message=f"{FILE_PATH} file loaded into bq.",
                        json_payload=json.dumps(
                                {"filenme": FILE_PATH,"time_created": timeCreated, "bucket": bucket}
                        )
            )
           
               
        return {
            "status": "success",
            "log_message": f"Processed XML file.loaded into bq.",
            "file_path": FILE_PATH,
            "time_created": timeCreated,
        }
        

    except Exception as e:
        stack_trace = traceback.format_exc()
        log_error(
            function_name="gcs_to_bq",
            endpoint="process-xml-files",
            log_message=str(e),
            error_type=type(e).__name__,
            stack_trace=stack_trace,
            json_payload=json.dumps(
                    {"filenme": FILE_PATH
                     ,"time_created": timeCreated}
            )
        )
        return {
            "status": "failed",
            "log_message": str(e),
            "error_type": type(e).__name__,
            "stack_trace": stack_trace,
            "file_path": FILE_PATH,
            "time_created": timeCreated,
        }
