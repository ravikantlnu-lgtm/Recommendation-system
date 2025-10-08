import concurrent.futures
import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import uuid

import functions_framework
from config import get_settings
from logging_config import log_default, log_error
from utils.send_relevent_project_to_queue_utils import process_one_project_search_pair
from services import BigQueryManager, GCPCloudTaskClient
from tqdm import tqdm
from utils import (
    find_nearby_branch_haversine,
    get_non_related_project_searches,
    get_processed_projects,
)
from utils.common import invoke_cloud_function
settings = get_settings()
bq_client = BigQueryManager(settings.BIGQUERY_DATASET)

    
def get_backfill_query():
    backfill_projects_query = """
    CREATE OR REPLACE TABLE `{project}.{dataset}.backfill_projects` AS
    WITH new_records AS (
        SELECT
        ProjectID,
        Title,
        Stage,
        Parameters_Parameter_BidDate,
        Valuation_Value,
        Parameters_Parameter_CommenceDate,
        sourceFileCreationTime,
        Addresses_Address,
        Details_Detail_Scope,
        ParentCategories_ParentCategory,
        URL,
        DocumentAvailability_Plans,
        DocumentAvailability_Specs,
        DocumentAvailability_Addenda,
        Parameters_Parameter_WorkType,
        Parameters_Parameter_FloorArea,
        Materials_Material,
        RSMeansMaterialDivisions_Division_Metals,
        RSMeansMaterialDivisions_Division_ThermalandMoistureProtection,
        RSMeansMaterialDivisions_Division_Openings,
        RSMeansMaterialDivisions_Division_Finishes,
        RSMeansMaterialDivisions_Division_Masonry,
        ParentCategories_PrimaryCategoryName,
        `Addresses_Address`[SAFE_OFFSET(0)].Longitude AS Longitude,
        `Addresses_Address`[SAFE_OFFSET(0)].Latitude AS Latitude,
        Companies
        FROM `{project}.{dataset}.{cc_table}`
        WHERE sourceFileCreationTime >=  DATETIME_SUB(CURRENT_DATETIME(), INTERVAL {backfill_days} DAY)
        QUALIFY ROW_NUMBER() OVER (PARTITION BY ProjectID ORDER BY sourceFileCreationTime DESC ) = 1 

    ),
    new_records_filter AS (
        SELECT nr.*
        FROM new_records nr
        WHERE
            CAST(nr.Valuation_Value AS FLOAT64) >= 1000000
            AND nr.Parameters_Parameter_BidDate IS NOT NULL
            AND nr.stage NOT IN ('Cancelled', 'Design Development', 'Disqualified Lead', 'Duplicate Project', 'Pre-Design', 'Schematic Design')
            AND (
                EXISTS (SELECT 1 FROM UNNEST(nr.Materials_Material) m INNER JOIN `{project}.{dataset}.{relevant_materials_table}` rm_general ON rm_general.division IS NULL AND m.code = rm_general.code AND m._ = rm_general.material)
                OR EXISTS (SELECT 1 FROM UNNEST(nr.RSMeansMaterialDivisions_Division_Metals) m INNER JOIN `{project}.{dataset}.{relevant_materials_table}` rm_metals ON rm_metals.division = 'Metals' AND m.code = rm_metals.code AND m._ = rm_metals.material)
                OR EXISTS (SELECT 1 FROM UNNEST(nr.RSMeansMaterialDivisions_Division_ThermalandMoistureProtection) m INNER JOIN `{project}.{dataset}.{relevant_materials_table}` rm_tmp ON rm_tmp.division = 'ThermalAndMoistureProtection' AND m.code = rm_tmp.code AND m._ = rm_tmp.material)
                OR EXISTS (SELECT 1 FROM UNNEST(nr.RSMeansMaterialDivisions_Division_Openings) m INNER JOIN `{project}.{dataset}.{relevant_materials_table}` rm_openings ON rm_openings.division = 'Openings' AND m.code = rm_openings.code AND m._ = rm_openings.material)
                OR EXISTS (SELECT 1 FROM UNNEST(nr.RSMeansMaterialDivisions_Division_Finishes) m INNER JOIN `{project}.{dataset}.{relevant_materials_table}` rm_finishes ON rm_finishes.division = 'Finishes' AND m.code = rm_finishes.code AND m._ = rm_finishes.material)
                OR EXISTS (SELECT 1 FROM UNNEST(nr.RSMeansMaterialDivisions_Division_Masonry) m INNER JOIN `{project}.{dataset}.{relevant_materials_table}` rm_masonry ON rm_masonry.division = 'Masonry' AND m.code = rm_masonry.code AND m._ = rm_masonry.material)
            )
            AND EXISTS (
                SELECT 1
                FROM UNNEST(nr.ParentCategories_ParentCategory) AS ParentCategory,
                    UNNEST(ParentCategory.SubCategories.SubCategory) AS SubCategory
                INNER JOIN `{project}.{dataset}.{relevant_categories_table}` rc ON ParentCategory.Name = rc.parent_category AND SubCategory = rc.value
                WHERE rc.category_type = 'sub_category'
            )
            AND EXISTS (
                SELECT 1
                FROM `{project}.{dataset}.{relevant_categories_table}` rc
                WHERE rc.category_type = 'primary' AND nr.ParentCategories_PrimaryCategoryName = rc.value
            )
    )
    SELECT
        ProjectID,
        Title,
        Stage,
        Parameters_Parameter_BidDate,
        Valuation_Value,
        Parameters_Parameter_CommenceDate,
        sourceFileCreationTime,
        Addresses_Address,
        Details_Detail_Scope,
        ParentCategories_ParentCategory,
        URL,
        DocumentAvailability_Plans,
        DocumentAvailability_Specs,
        DocumentAvailability_Addenda,
        Parameters_Parameter_WorkType,
        Parameters_Parameter_FloorArea,
        Companies
    FROM new_records_filter n
    ;"""

    return backfill_projects_query


@functions_framework.http
def backfill_projects(request):
    try:
        request_json = request.get_json(silent=True)
        if request_json:
            event = request_json.get("event", "No event provided")
            force_process = event.get("force_process", False)
        else:
            log_error(
                function_name="backfill_projects",
                endpoint="backfill-projects",
                log_message="No JSON payload received.",
            )

            return {
                "status": "failed",
                "log_message": "No JSON payload received.",
            }

        log_default(
            log_message="backfill_projects function started......",
        )
        task_client = GCPCloudTaskClient(
            project=settings.PROJECT_ID,
            location=settings.CLOUD_TASK_LOCATION,
            queue=settings.CLOUD_TASK_SEND_PROJECT_TO_QUEUE_QUEUE,
            service_account_email=settings.WORKFLOW_INVOCATION_SA,
        )

        WORKFLOW_INVOCATION_URL = f"https://workflowexecutions.googleapis.com/v1/projects/{settings.PROJECT_ID}/locations/{settings.WORKFLOW_INVOCATION_LOCATION}/workflows/{settings.WORKFLOW_INVOCATION_NAME}/executions"

        backfill_days = event["backfill_days"]
        search_ids = event.get("search_ids").strip() if event.get("search_ids") else None

        if search_ids:
            payload = {
                "event" : {
                    "name" : "project backfill",
                    "timeCreated": datetime.now().isoformat()
                }
            }
            # Invoking search-teritory-updates cloud function to sync search table.
            invoke_cloud_function(
                settings.SEARCH_TERRITORY_UPDATES_CLOUD_FUNCTION_URL,
                payload = payload,
                wait_to_complete = True
            )

        log_default(
            log_message="Fetching relevant project candidates from BigQuery for backfill...",
            json_payload=json.dumps({"backfill_days": backfill_days}),
        )

        backfill_projects_query = get_backfill_query().format(
            project=settings.PROJECT_ID,
            dataset=settings.BIGQUERY_DATASET,
            cc_table=settings.CC_FEED_TABLE_ID,
            relevant_categories_table=settings.RELEVANT_CATEGORIES_TABLE_ID,
            relevant_materials_table=settings.RELEVANT_MATERIALS_TABLE_ID,
            backfill_days=backfill_days,
        )
        bq_client.query_table(backfill_projects_query)

        query = f"""
                SELECT 
                    ProjectID, 
                    sourceFileCreationTime,
                    `Addresses_Address`[SAFE_OFFSET(0)].Longitude AS Longitude,
                    `Addresses_Address`[SAFE_OFFSET(0)].Latitude AS Latitude,
                FROM {settings.BIGQUERY_DATASET}.backfill_projects"""
        backfill_projects_ls = bq_client.query_table(query=query, to_dataframe=True)

        log_default(
            log_message="Fetching territories from BigQuery...",
            json_payload=json.dumps({"backfill_days": backfill_days}),
        )

        # # Get territories
        territories_query = f"SELECT id as territory_id, latitude as lat, longitude as lon FROM {settings.BIGQUERY_DATASET}.{settings.TERRITORIES_TABLE_ID}"
        territories = bq_client.query_table(territories_query, to_dataframe=True)

        log_default(
            log_message="Finding nearby branches for each project candidate...",
            json_payload=json.dumps({"backfill_days": backfill_days}),
        )
        # Assign territories to project_candidates
        backfill_projects_ls["assigned_branches"] = backfill_projects_ls.apply(
            lambda x: find_nearby_branch_haversine(
                row=x,
                df_branch=territories,
                radius_miles=settings.RADIUS_MILES,
                max_branches=settings.MAX_BRANCHES,
            ),
            axis=1,
        )

        log_default(
            log_message="Fetching searches from BigQuery...",
            json_payload=json.dumps({"backfill_days": backfill_days}),
        )
        # Get searches
        search_id_filter = ''
        # Creating search filter to backfill projects for particular searchs
        if search_ids:
            search_id_filter = ','.join(f"'{id}'" for id in search_ids.split(','))
            search_id_filter = f"WHERE s.id in ({search_id_filter})"

        searches_query = f"""SELECT id AS search_id, territory_id FROM `{settings.BIGQUERY_DATASET}.{settings.SEARCHES_TABLE_ID}` s
            left join `{settings.BIGQUERY_DATASET}.{settings.SEARCH_TERRITORY_TABLE_ID}` m
            on s.id = m.search_id
            {search_id_filter}"""
        search_id_ls = bq_client.query_table(searches_query)

        project_relevance_index = get_processed_projects(
            settings=settings,
            FILE_PATH=None,
            TIME_CREATED=None,
            bq_client=bq_client,
            backfill_flag=True,
        )
        # Get non-related project searches
        non_related_project_searches_index = get_non_related_project_searches(
            settings=settings,
            FILE_PATH=None,
            TIME_CREATED=None,
            bq_client=bq_client,
            backfill_flag=True,
        )

        log_default(
            log_message="Sending projects to the queue...",
            json_payload=json.dumps({"backfill_days": backfill_days}),
        )
        total_project_search_cnt = 0
        futures = []
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=settings.MAX_WORKERS
        ) as executor:
            for _, project_candidate in backfill_projects_ls.iterrows():
                for search in search_id_ls:
                    future = executor.submit(
                        process_one_project_search_pair,
                        project_candidate,
                        search,
                        task_client,
                        WORKFLOW_INVOCATION_URL,
                        project_relevance_index,
                        non_related_project_searches_index,
                        force_process=force_process,
                    )
                    futures.append(future)

        # Wrap as_completed with tqdm for progress bar
        for future in tqdm(
            concurrent.futures.as_completed(futures),
            total=len(futures),
            desc="backfill_projects Processing project-search pairs",
        ):
            try:
                count = future.result()
                total_project_search_cnt += count
            except Exception as e:
                log_error(
                    function_name="backfill_projects",
                    endpoint="backfill_projects",
                    log_message=f"Task generation failed: {e}",
                    error_type=type(e).__name__,
                    stack_trace=traceback.format_exc(),
                )

        

        payload = {
            "event":{
                "name": "project backfill",
                "timeCreated": datetime.now().isoformat(),
                "backfill": True,
                "search_ids" : search_ids
            }
        }

        # Invoking the trigger-batch-upsert Cloud Function. 
        # Once all projects are processed by the project_id workflow, it will trigger the batch-upsert-lead Cloud Function.
        invoke_cloud_function(
            settings.TRIGGER_BATCH_UPSERT_CLOUD_FUNCTION_URL,
            payload=payload,
            wait_to_complete= False
        )

        return {
            "status": "success",
            "log_message": f"backfill_projects completed successfully",
            "backfill_days": backfill_days,
        }

    except Exception as e:
        stack_trace = traceback.format_exc()
        log_error(
            function_name="backfill_projects",
            endpoint="backfill-projects",
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
