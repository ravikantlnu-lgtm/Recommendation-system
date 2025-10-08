import functions_framework

import traceback
import json
import pandas as pd
from google.cloud import bigquery
from dateutil import parser

from config import get_settings
from services import BigQueryManager
from logging_config import log_default, log_error
from utils.common import truncate_iso_to_seconds
from utils.deduplicate_projects_utils import process_one_project_pair_deduplication, source_column_names


settings = get_settings()
big_query_client = BigQueryManager(dataset_id=settings.BIGQUERY_DATASET)


@functions_framework.http
def resolve_potential_duplicates(request):
    try:
        request_json = request.get_json(silent=True)
        if not request_json:

            log_error(
                function_name="resolve_potential_duplicates",
                endpoint="resolve-potential-duplicates",
                log_message="No JSON payload received.",
            )
            return {
                "status": "failed",
                "log_message": "No JSON payload received.",
            }
        FILE_PATH = request_json["name"]
        TIME_CREATED = truncate_iso_to_seconds(request_json["timeCreated"])
        bucket = request_json.get("bucket")
        batch_id = request_json["batch_id"]
        distance = request_json["distance"]

        project_1 = request_json['project_1']
        project_2 = request_json['project_2']
        project_1_source = request_json['project_1_source']
        project_2_source = request_json['project_2_source']

        # calling llm modle to compare 
        log_default(
            log_message=f"Calling llm modle for project comparison."
            ,json_payload=json.dumps(
                  {
                       "file_path": FILE_PATH,
                       "timeCreated": TIME_CREATED,
                       "bucket": bucket,
                       "batch_id": batch_id
                  }
             )
        )

        result = process_one_project_pair_deduplication(
            project_1_data=project_1,
            project_2_data=project_2,
            project_1_source=project_1_source,
            project_2_source=project_2_source,
            distance=distance
        )
        

        result = result._asdict()

        table_id = settings.LLM_DEDUPLICATION_RESULT_TABLE_ID
        rows_to_insert = []


        log_default(
            log_message=f"Inserting result of llm model to LLM_DEDUPLICATION_RESULT table."
            ,json_payload=json.dumps(
                  {
                       "file_path": FILE_PATH,
                       "timeCreated": TIME_CREATED,
                       "bucket": bucket,
                       "batch_id": batch_id
                  }
             )
        )
        
        rows_to_insert.append(
            {
                "project_id": project_1[source_column_names[project_1_source]['id_col']],
                "potential_match_id": project_2[source_column_names[project_2_source]['id_col']],
                "project_source": project_1_source,
                "potential_match_source": project_2_source,
                "sourceFileCreationTime": parser.parse(project_1['sourceFileCreationTime']) ,
                "potential_match_sourceFileCreationTime": parser.parse(project_2['sourceFileCreationTime']) ,
                "llm_result": result['match'],
                "llm_reasoning": result['reasoning'],
                "batch_id": batch_id
            }
        )
        rows_to_insert_df = pd.DataFrame(rows_to_insert)
        schema = big_query_client.get_schema(table_id)
        schema = [field for field in schema if field.name.lower() not in  ["insert_timestamp","existing_primary_project_id"]]
        job_config = bigquery.LoadJobConfig(
            write_disposition="WRITE_APPEND",
            schema_update_options=[bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION],
            schema = schema
        )
        result = big_query_client.load_from_dataframe(table_id, rows_to_insert_df, job_config)
        

        log_default(
                log_message=f"New {len(rows_to_insert)} row/rows have been added to the {table_id} table.",
            )

        return {
            "status": "success",
            "log_message": f"resolve_potential_duplicates completed successfully",
            "filename": FILE_PATH,
            "time_created": TIME_CREATED,
        }
        
    except Exception as e:
        stack_trace = traceback.format_exc()
        log_error(
            function_name="resolve_potential_duplicates",
            endpoint="resolve-potential-duplicates",
            log_message=str(e),
            error_type=type(e).__name__,
            stack_trace=stack_trace,
            json_payload=json.dumps(request_json),
        )
        return {
            "status": "failed",
            "log_message": str(e),
            "error_type": type(e).__name__,
            "stack_trace": stack_trace,
            "filename": request_json.get('name'),
            "time_created": request_json.get('timeCreated'),
            "bucket": request_json.get("bucket"),
            "batch_id": request_json.get("batch_id")
        }
