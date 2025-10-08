import functions_framework

import traceback
import json
import numpy as np
import pandas as pd
from fuzzywuzzy import fuzz
from google.cloud import bigquery
from dateutil import parser

from config import get_settings
from services import BigQueryManager, GCPCloudTaskClient, GCSFileManager
from logging_config import log_default, log_error
from utils.common import truncate_iso_to_seconds, invoke_cloud_function


settings = get_settings()
big_query_client = BigQueryManager(dataset_id=settings.BIGQUERY_DATASET)


CC_QUERY = """WITH OwnerName
AS (
	SELECT ProjectID,
		ARRAY_AGG(DISTINCT company.Name) AS owner_names,
	FROM (
            SELECT ProjectID,
                Companies
            FROM `{project}.{dataset}.{cc_table}` CC
            WHERE {Filter}
		),
		UNNEST(Companies) AS company_wrap, 
		UNNEST(company_wrap.Company) AS company
	WHERE INSTR(lower(company.ROLE), "owner") > 0
    GROUP BY ProjectID
	),
cc_data
AS (
	SELECT CC.ProjectID,
		Title,
		Addresses_Address [SAFE_OFFSET(0)].Latitude Latitude,
		Addresses_Address [SAFE_OFFSET(0)].Longitude Longitude,
		Details_Detail_Scope,
		Details_Detail_Notes,
		Details_Detail_Details,
		Parameters_Parameter_Ownership,
		Parameters_Parameter_WorkType,
		ParentCategories_ParentCategory,
		ParentCategories_PrimaryCategoryName,
		Valuation_Value,
		OwnerName.owner_names,
        cast(sourceFileCreationTime as STRING) sourceFileCreationTime,
		'construct_connect' AS source
	FROM `{project}.{dataset}.{cc_table}` CC
	LEFT JOIN OwnerName ON OwnerName.ProjectID = CC.ProjectID
	WHERE {Filter} 
    QUALIFY ROW_NUMBER() OVER (PARTITION BY CC.ProjectID ORDER BY sourceFileCreationTime DESC) = 1
	)
{select_part}
"""

DODGE_QUERY = """
WITH OwnerName
AS (
	SELECT DRNumber,
		ARRAY_AGG(DISTINCT company.CompanyName) AS owner_names,
	FROM (
		SELECT DRNumber,
			VersionNumber,
			Companies
		FROM `{project}.{dataset}.{dodge_table}` DD
		WHERE {Filter}
		),
		UNNEST(Companies.company) AS company
	WHERE INSTR(lower(company.FactorType), "owner") > 0 
    GROUP BY DRNumber
	),
dodge_data
AS (
	SELECT DD.DRNumber,
		ProjectTitle,
		cast(Lat AS float64) Lat,
		cast(Long AS float64) Long,
		StatusText,
		FeaturesInfo,
		OwnershipType,
		TypeOfWork,
		MarketSegment,
		PrimaryProjectType,
		Valuation,
		OwnerName.owner_names,
        cast(sourceFileCreationTime as STRING) sourceFileCreationTime,
		'dodge' AS source
	FROM `{project}.{dataset}.{dodge_table}` DD
	LEFT JOIN OwnerName ON OwnerName.DRNumber = DD.DRNumber
	WHERE {Filter}
    QUALIFY ROW_NUMBER() OVER ( PARTITION BY DD.DRNumber ORDER BY VersionNumber DESC ) = 1
	)
{select_part}
"""



@functions_framework.http
def deduplicate_projects_batch(request):
    """HTTP Cloud Function.
    This Cloud Function processes a batch of projects from the projects_for_deduplication BigQuery table.
    It applies matching logic to identify and categorize project pairs into Clear Matches, Potential Duplicates (for LLM review), and Clear Uniques, 
    enabling accurate deduplication before downstream processing.
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
        if request_json:
                event = request_json.get("event", "No event provided")
        else:
            log_error(
                function_name="deduplicate_projects_batch",
                endpoint="deduplicate-projects-batch",
                log_message="No JSON payload received.",
            )
            return {
                "status": "failed",
                "log_message": "No JSON payload received.",
            }
        
        FILE_PATH = event["name"]
        TIME_CREATED = truncate_iso_to_seconds(event["timeCreated"])
        bucket = event.get("bucket")
        batch_id = event["batch_id"]
        distance_threshold_miles = 0.05
        fuzzy_threshold = 50
        log_context = {
                    "file_path": FILE_PATH,
                    "timeCreated": TIME_CREATED,
                    "bucket": bucket,
                    "batch_id": batch_id
                }

        # Key to remove from project data before sending to llm comparision. 
        keys_to_remove = ["pfd_project_id","pfd_ProjectTitle","distance_in_miles","title_match_ratio"]

        # deduplication resolution workflow url
        WORKFLOW_INVOCATION_URL = f"https://workflowexecutions.googleapis.com/v1/projects/{settings.PROJECT_ID}/locations/{settings.WORKFLOW_INVOCATION_LOCATION}/workflows/{settings.WORKFLOW_DEDUPLICATION_RESOLUTION_NAME}/executions"
        # list to store created cloud task queue
        created_task_ls = []
        # Create a Cloud Task client for send project to queue
        task_client = GCPCloudTaskClient(
            project=settings.PROJECT_ID,
            location=settings.CLOUD_TASK_LOCATION,
            queue=settings.CLOUD_TASK_SEND_PROJECT_TO_QUEUE_QUEUE,
            service_account_email=settings.WORKFLOW_INVOCATION_SA,
        )

        gcs_client = GCSFileManager(settings.GCS_BUCKET)
        
        # Decideciding delta file source
        if bucket == settings.GCS_SOURCE_BUCKET:
            source = "construct_connect"
            cross_source = "dodge"
            id_col = "ProjectID"
            cross_id_col = "DRNumber"
            
        elif bucket == settings.DODGE_GCS_SOURCE_BUCKET:
            source = "dodge"
            cross_source = "construct_connect"
            id_col = "DRNumber"
            cross_id_col = "ProjectID"
            
        else:
            log_error(
                function_name="deduplicate_projects_batch",
                endpoint="deduplicate-projects-batch",
                log_message=f"Unsupported bucket: {bucket}. Expected {settings.GCS_SOURCE_BUCKET} or {settings.DODGE_GCS_SOURCE_BUCKET}"

            )
            return {
                "status": "failed",
                "log_message": f"Unsupported bucket: {bucket}. Expected {settings.GCS_SOURCE_BUCKET} or {settings.DODGE_GCS_SOURCE_BUCKET}",
            }
    
        # Query to fetch project_candidates details store in project_for_deduplication table.
        query = f"""
                SELECT project_id as pfd_project_id, 
                    ProjectTitle as pfd_ProjectTitle,
                    lat as pfd_lat,
                    long as pfd_long,
                    cast(sourceFileCreationTime as string) sourceFileCreationTime,
                    data_source as pdf_source
                FROM `{settings.BIGQUERY_DATASET}.{settings.PROJECTS_FOR_DEDUPLICATION_TABLE_ID}`
                WHERE batch_id = '{batch_id}';
            """
        log_default( log_message= f"Executing query to fetch projects for batch {batch_id}", json_payload=json.dumps(log_context) )


        projects_for_deduplication_df = big_query_client.query_table(
             query=query,
             to_dataframe=True
        )
        if projects_for_deduplication_df.empty:
            log_default( log_message=f"No projects found for batch {batch_id}", json_payload=json.dumps(log_context) )
            return {
                "status": "success",
                "log_message": f"No projects found for batch {batch_id}",
                "filename": FILE_PATH,
                "time_created": TIME_CREATED,
                "bucket": bucket,
                "batch_id": batch_id
                }
        

# ---------------------Identifying duplicate projects by comparing delta file with cross data source(construnct_connect/dodge) feed table ------------------------------#
        
        if cross_source == "construct_connect":
            title_col = "Title"
            # timeIntervalFilter of last_30_days_cc_query.
            cc_timeIntervalFilter = "Date(sourceFileCreationTime) >=  DATE(DATETIME_SUB(CURRENT_DATETIME(), INTERVAL 30 DAY))"
            # Select part of last_30_days_cc_query.
            cc_select_part = f"""
            SELECT project_id AS pfd_project_id,
                pfd.ProjectTitle AS pfd_ProjectTitle,
                potential_match.*,
                ST_DISTANCE(ST_GEOGPOINT(cast(pfd.long as float64), cast(pfd.lat as float64)), ST_GEOGPOINT(potential_match.Longitude, potential_match.Latitude)) / 1609.34 AS distance_in_miles
            FROM `{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.{settings.PROJECTS_FOR_DEDUPLICATION_TABLE_ID}` pfd,
                cc_data potential_match
            WHERE batch_id = '{batch_id}'
                AND ST_DISTANCE(ST_GEOGPOINT(cast(pfd.long as float64), cast(pfd.lat as float64)), ST_GEOGPOINT(potential_match.Longitude, potential_match.Latitude)) / 1609.34 < {distance_threshold_miles}
                AND project_id != ProjectID
            ORDER BY 1"""

            # Query: Join project_for_deduplication with the most recent 30-day ConstructConnect projects.
            # Calculate the distance between projects using BigQuery geography functions.
            # Filter out records where the distance is greater than 0.05 miles.
            # In short, this returns projects with potential matches that satisfy the distance criteria.
            last_30_days_data_query = CC_QUERY.format(
                project=settings.PROJECT_ID,
                dataset=settings.BIGQUERY_DATASET,
                cc_table=settings.CC_FEED_TABLE_ID,
                select_part=cc_select_part,
                Filter=cc_timeIntervalFilter
            )
        elif cross_source == "dodge":
            title_col = "ProjectTitle"
            # # Getting most recent projects data of last 30 days dodge data.
            dodge_Filter = "Date(sourceFileCreationTime) >=  DATE(DATETIME_SUB(CURRENT_DATETIME(), INTERVAL 30 DAY))"
            dodge_select_part = f"""
                    SELECT project_id AS pfd_project_id,
                        pfd.ProjectTitle AS pfd_ProjectTitle,
                        potential_match.*,
                        ST_DISTANCE(ST_GEOGPOINT(cast(pfd.long as float64), cast(pfd.lat as float64)), ST_GEOGPOINT(cast(potential_match.Long as float64), cast(potential_match.lat as float64))) / 1609.34 AS distance_in_miles
                    FROM `{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.{settings.PROJECTS_FOR_DEDUPLICATION_TABLE_ID}` pfd,
                        dodge_data potential_match
                    WHERE batch_id = '{batch_id}'
                        AND ST_DISTANCE(ST_GEOGPOINT(cast(pfd.long as float64), cast(pfd.lat as float64)), ST_GEOGPOINT(cast(potential_match.Long as float64), cast(potential_match.lat as float64))) / 1609.34 < {distance_threshold_miles}
                        AND project_id != DRNumber
                    ORDER BY 1
            """
            # Query: Join project_for_deduplication with the most recent 30-day Dodge projects.
            # Calculate the distance between projects using BigQuery geography functions.
            # Filter out records where the distance is greater than 0.05 miles.
            # In short, this returns projects with potential matches that satisfy the distance criteria.
            last_30_days_data_query = DODGE_QUERY.format(
                project=settings.PROJECT_ID,
                dataset=settings.BIGQUERY_DATASET,
                dodge_table=settings.DODGE_FEED_TABLE_ID,
                select_part=dodge_select_part,
                Filter=dodge_Filter
            )

    
        log_default( log_message=f"Getting last 30 days projects from {cross_source}  Bigquery table.",json_payload=json.dumps(log_context) )


        df = big_query_client.query_table(
             query=last_30_days_data_query,
             to_dataframe=True
        )
        

        
        
        potential_duplicates_project_ids_ls = []
        if not df.empty: 
            log_default( log_message=f"Calculating title_match_ratio between projects_for_deduplication and construct_connect projects." , json_payload=json.dumps(log_context) )
        # Calculating title_match_ratio using fuzzy logic
            df['title_match_ratio'] = df.apply(
                    lambda row: fuzz.partial_ratio(row['pfd_ProjectTitle'], row[title_col]),
                    axis=1
                )
            # Selecting only projects with title_match_ratio greater than 50%.
            df = df[df['title_match_ratio'] > fuzzy_threshold]

            # Generating list of project IDs qualifying based on title and distance match
            potential_duplicates_project_ids_ls = df['pfd_project_id'].to_list()


        # Retrieving delta file project details from BigQuery for projects that meet title and distance matching criteria.
        if source == "construct_connect":
            cc_select_part = f""" SELECT  * FROM cc_data"""
            cc_Filter = f"sourceFileCreationTime = '{TIME_CREATED}' AND sourceFile = '{FILE_PATH}' AND CC.ProjectID in UNNEST({potential_duplicates_project_ids_ls})"
            query = CC_QUERY.format(
                project=settings.PROJECT_ID,
                dataset=settings.BIGQUERY_DATASET,
                cc_table=settings.CC_FEED_TABLE_ID,
                select_part=cc_select_part,
                Filter=cc_Filter
            )


        elif source == "dodge":
            dodge_select_part = f""" SELECT  * FROM dodge_data"""
            dodge_Filter = f"sourceFileCreationTime = '{TIME_CREATED}' AND sourceFile = '{FILE_PATH}' AND DD.DRNumber in UNNEST({potential_duplicates_project_ids_ls})"
            
            query = DODGE_QUERY.format(
                project=settings.PROJECT_ID,
                dataset=settings.BIGQUERY_DATASET,
                dodge_table=settings.DODGE_FEED_TABLE_ID,
                Filter=dodge_Filter,
                select_part=dodge_select_part
            )

        if len(potential_duplicates_project_ids_ls) > 0:

            duplicat_project_df = big_query_client.query_table(
                query=query,
                to_dataframe=True
            )

            log_default( log_message=f"Creating task for potential matches with construct connect project." , json_payload=json.dumps(log_context) )
            # Sending project and its potential matches to 'deduplication-resolution-workflow' to perform LLM-based deduplication resolution.
            # Creating task 
            for _, project in df.iterrows():

                project_1 = duplicat_project_df[duplicat_project_df[id_col] == project['pfd_project_id']].iloc[0]
                project_1 = json.loads(project_1.to_json())

                project_2 = df[df[cross_id_col] == project[cross_id_col]].iloc[0]
                project_2 = json.loads(project_2.to_json())

                
                for key in keys_to_remove:
                    project_2.pop(key, None)
                

                message = {
                    "project_1": project_1,
                    "project_2": project_2,
                    "project_1_source": project_1['source'],
                    "project_2_source": project_2['source'],
                    "distance": project['distance_in_miles'],
                    "name": FILE_PATH,
                    "timeCreated": TIME_CREATED,
                    "bucket": bucket,
                    "batch_id": batch_id
                }

                response = task_client.create_task(url=WORKFLOW_INVOCATION_URL, payload=message)
                created_task_ls.append(str(response.name))



        # Creating a list of project IDs that are potential duplicates.

        potential_duplicates_project_ids_ls = list(set(potential_duplicates_project_ids_ls))

        table_id = settings.LLM_DEDUPLICATION_RESULT_TABLE_ID

        log_default(
            log_message= f"Inserting non-duplicate project details to BigQuery",
            json_payload=json.dumps(
                {
                    "file_path": FILE_PATH,
                    "timeCreated": TIME_CREATED,
                    "bucket": bucket,
                    "batch_id": batch_id
                }
            )
        )
        if not projects_for_deduplication_df.empty:
            projects_for_deduplication_df = projects_for_deduplication_df[~projects_for_deduplication_df['pfd_project_id'].isin(potential_duplicates_project_ids_ls)]

            rows_to_insert = []
            for _ , project in projects_for_deduplication_df.iterrows():
                rows_to_insert.append(
                    {
                        "project_id": project['pfd_project_id'],
                        "potential_match_id": None,
                        "project_source": source,
                        "potential_match_source": None,
                        "sourceFileCreationTime": parser.parse(project['sourceFileCreationTime']),
                        "potential_match_sourceFileCreationTime" : None,
                        "llm_result": 'no_match',
                        "llm_reasoning": "distance/title criteria not satisfied.",
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

        created_task_dict = {"tasks":created_task_ls}
        # Uploading created task list in GCS. To used further to check task in cloud task queue.
        uri = gcs_client.upload_data(
            file_path=f"cloud_task/{FILE_PATH}_deduplicate_projects_task.json",
            data=created_task_dict
        )


        payload = {
                "event": {
                    "name": FILE_PATH,
                    "timeCreated": TIME_CREATED,
                    "workflow_name": settings.WORKFLOW_DEDUPLICATION_RESOLUTION_NAME,
                    "batch_id" : batch_id,
                    "bucket": bucket
                }
            }
        # Triggering TRIGGER_BATCH_UPSERT_CLOUD_FUNCTION_URL to monitor execution of  DEDUPLICATION_RESOLUTION workflow and task in cloud task queue.
        invoke_cloud_function(settings.TRIGGER_BATCH_UPSERT_CLOUD_FUNCTION_URL, payload)

        return {
            "status": "success",
            "log_message": f"deduplicate_projects_batch completed successfully.",
            "file_path": FILE_PATH,
            "time_created": TIME_CREATED,
        }
             
        
    except Exception as e:
        stack_trace = traceback.format_exc()
        log_error(
            function_name="deduplicate_projects_batch",
            endpoint="deduplicate-projects-batch",
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
