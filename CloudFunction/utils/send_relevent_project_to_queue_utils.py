import math
from datetime import datetime
import concurrent.futures
import json
import traceback
from datetime import datetime


import requests
from config import get_settings
from utils.common import get_secret
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from logging_config import log_default, log_error
from requests.exceptions import ReadTimeout, RequestException

from tqdm import tqdm

from utils.common import haversine_distance_miles_numpy


settings = get_settings()

import numpy as np

def find_nearby_branch_haversine(row, df_branch, radius_miles=60, max_branches=5):
    """
    Find all branches within specified radius for each location in df_bq using haversine distance

    Args:
        df_bq: DataFrame with customer/location data
        df_branch: DataFrame with branch locations
        radius_miles: Search radius in miles
        max_branches: Maximum number of nearby branches to return

    Returns:
        pd.Series containing dictionaries of nearby warehouses and their distances
    """
    # Convert warehouse coordinates to numpy arrays for vectorized calculation
    branch_lats = df_branch["lat"].values
    branch_longs = df_branch["lon"].values

    distances = haversine_distance_miles_numpy(
        row["Latitude"], row["Longitude"], branch_lats, branch_longs
    )
    df_branch["distance"] = distances.round(2)
    nearby_pairs = (
        df_branch[df_branch["distance"] <= radius_miles]
        .sort_values("distance")
        .head(max_branches)
    )
    nearby_pairs = nearby_pairs[["territory_id", "distance"]].to_dict(orient="records")

    # Return np.nan if no nearby branches are found
    if not nearby_pairs:
        return np.nan

    return nearby_pairs


def get_processed_projects(
    settings, FILE_PATH, TIME_CREATED, bq_client, bucket, backfill_flag=False
):
    "Fetching project information from the project_relevance table for projects listed in the delta files"
    project_relevance_table = f"{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.{settings.PROJECT_RELEVANCE_TABLE_ID}"

    if bucket == settings.GCS_SOURCE_BUCKET:
        project_id_col = "ProjectId"
        source_table_id = f"{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.{settings.CC_FEED_TABLE_ID}"
    elif bucket == settings.DODGE_GCS_SOURCE_BUCKET:
        project_id_col = "DRNumber"
        source_table_id = f"{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.{settings.DODGE_FEED_TABLE_ID}"

        
    backfill_projects = (
        f"{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.backfill_projects"
    )

    query = f"""
                SELECT DISTINCT project_id,
                search_id,
                territory_id,
                time_created
            FROM {project_relevance_table}
            WHERE (
                    project_id,
                    time_created
                    ) IN (
                    SELECT (
                            CAST({project_id_col} AS STRING),
                            sourceFileCreationTime
                            )
                    FROM {source_table_id}
                    WHERE sourcefile = '{FILE_PATH}'
                        AND sourceFileCreationTime = '{TIME_CREATED}'
                    )"""
    if backfill_flag:
        query = f"""
                SELECT DISTINCT project_id,
                search_id,
                territory_id,
                time_created
            FROM {project_relevance_table}
            WHERE (
                    project_id,
                    time_created
                    ) IN (
                    SELECT (
                            CAST(projectid as STRING),
                            sourceFileCreationTime
                            )
                    FROM {backfill_projects}
                    )
        """
    result = bq_client.query_table(query=query)
    project_relevance_index = {
        (d["project_id"], d["search_id"], d["territory_id"], d["time_created"])
        for d in result
    }

    return project_relevance_index


def get_non_related_project_searches(
    settings, FILE_PATH, TIME_CREATED, bq_client, bucket, backfill_flag=False
):
    """
    Fetches DISTINCT (project_id, search_id, time_created) combinations
    marked as 'NO' in the assigned_search table for the specific projects
    listed in the delta files. Territory is ignored for this check.
    """
    assigned_search_table = f"{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.{settings.ASSIGNED_SEARCH_TABLE_ID}"

    if bucket == settings.GCS_SOURCE_BUCKET:
        project_id_col = "ProjectId"
        source_table_id = f"{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.{settings.CC_FEED_TABLE_ID}"
    elif bucket == settings.DODGE_GCS_SOURCE_BUCKET:
        project_id_col = "DRNumber"
        source_table_id = f"{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.{settings.DODGE_FEED_TABLE_ID}"

    
    backfill_projects = (
        f"{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.backfill_projects"
    )

    query = f"""
        SELECT DISTINCT -- Ensure uniqueness at the project/search/time level
            asn.project_id,
            asn.search_id,
            asn.time_created
        FROM {assigned_search_table} AS asn
        WHERE
            asn.is_related = 'NO'
            -- Filter only for projects present in the current delta file batch
            AND (asn.project_id, asn.time_created) IN (
                SELECT
                    (
                        CAST(ccf.{project_id_col} as STRING),
                        ccf.sourceFileCreationTime
                    )
                FROM {source_table_id} AS ccf
                WHERE ccf.sourcefile = '{FILE_PATH}'
                  AND ccf.sourceFileCreationTime = '{TIME_CREATED}'
            )
            AND asn.project_id IS NOT NULL -- Add basic NULL checks for key parts
            AND asn.search_id IS NOT NULL
            AND asn.time_created IS NOT NULL
    """
    if backfill_flag:
        query = f"""
            SELECT DISTINCT -- Ensure uniqueness at the project/search/time level
                asn.project_id,
                asn.search_id,
                asn.time_created
            FROM {assigned_search_table} AS asn
            WHERE
                asn.is_related = 'NO'
                -- Filter only for projects present in the current delta file batch
                AND (asn.project_id, asn.time_created) IN (
                    SELECT
                        (
                           CAST(bp.projectid as STRING),
                           bp.sourceFileCreationTime
                        )
                    FROM {backfill_projects} bp
                )
                AND asn.project_id IS NOT NULL -- Add basic NULL checks for key parts
                AND asn.search_id IS NOT NULL
                AND asn.time_created IS NOT NULL
        """
    try:
        result = bq_client.query_table(query=query)
        # Create a set of 3-element tuples for efficient lookup
        # Renamed set for clarity
        non_related_project_search_index = {
            (
                d["project_id"],
                d["search_id"],
                d["time_created"].replace(tzinfo=None) if d["time_created"] else None,
            )
            for d in result  # Already distinct from SQL
        }
    except Exception as e:
        print(f"Error fetching non-related project-searches: {e}")
        non_related_project_search_index = set()

    return non_related_project_search_index


def should_process_project(
    project_id,
    search_id,
    territory_id,
    creation_time,
    project_relevance_index,
    non_related_project_searches_index,
    force_process=False,  # Add new parameter with default
):
    """
    Determines if a project should be processed based on existing records.

    Args:
        project_id (str): The project identifier
        search_id (str): The search identifier
        territory_id (str, optional): The territory identifier. Can be None.
        creation_time (datetime): The creation time
        project_relevance_index (set): Set of processed project tuples
        non_related_project_searches_index (set): Set of non-related project tuples
        force_process (bool): If True, bypass checks and always return True.

    Returns:
        bool: True if the project should be processed, False otherwise
    """
    # If force_process is True, skip checks and return True
    if force_process:
        return True

    # Check if project already exists in project_relevance for this territory
    project_already_processed = (
        project_id,
        search_id,
        territory_id,
        creation_time,
    ) in project_relevance_index

    # Check if project is marked as non-related for this search
    project_non_related = (
        project_id,
        search_id,
        creation_time,
    ) in non_related_project_searches_index

    # Return True if the project should be processed (not already processed and not marked non-related)
    return not (project_already_processed or project_non_related)

def invoke_cloud_function(CLOUD_FUNCTION_URL, payload=None):
    # Load service account credentials
    service_account_info = json.loads(get_secret(project_number=settings.PROJECT_ID, 
                                                 secret_name="default-service-account"))
    credentials = service_account.IDTokenCredentials.from_service_account_info(
        service_account_info, target_audience=CLOUD_FUNCTION_URL
    )
    # Refresh the credentials to get the identity token
    credentials.refresh(Request())
    token = credentials.token
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        # Fire-and-forget: short timeout and no response handling
        requests.post(
            CLOUD_FUNCTION_URL,
            headers=headers,
            json=payload,
            timeout=5,  # Just enough to send the request
        )
    except ReadTimeout:
        # Read timeout is expected in fire-and-forget mode
        pass
    except RequestException as e:
        # Raise all other exceptions
        raise RuntimeError(f"Cloud Function trigger failed: {e}")
    log_default(
        log_message="Cloud Function triggered successfully",
        json_payload=json.dumps(
            {"cloud_function_url": CLOUD_FUNCTION_URL, "payload": payload}
        ),
    )


def process_one_project_search_pair(
    project_candidate,
    search,
    search_product_materials_df, 
    task_client,
    WORKFLOW_INVOCATION_URL,
    project_relevance_index,
    non_related_project_searches_index,
    batch_id,
    force_process=False,
):

    project_id = project_candidate["ProjectID"]
    search_id = search["search_id"]
    creation_time_str = project_candidate["sourceFileCreationTime"]


    # Handle projects with and without assigned branches
    if str(project_candidate["assigned_branches"]) == "nan":
        # For projects without branches, check if the project should be processed
        if should_process_project(
            project_id,
            search_id,
            None,
            creation_time_str,
            project_relevance_index,
            non_related_project_searches_index,
            force_process=force_process,
        ):

            # If the search has a territory, skip the project candidate
            if search["territory_id"]:
                return 0

            # Submit task to process project to queue without territory
            processed_projects_cnt = process_project_without_territory(
                project_id,
                search_id,
                search_product_materials_df,
                creation_time_str,
                task_client,
                WORKFLOW_INVOCATION_URL,
                batch_id
            )

            return processed_projects_cnt

        # Skip project
        else:
            return 0

    else:
        # For projects with branches, check each branch
        territories_to_process = []

        for branch in project_candidate["assigned_branches"]:
            territory_id = branch["territory_id"]

            # Check if this territory should be processed
            if should_process_project(
                project_id,
                search_id,
                territory_id,
                creation_time_str,
                project_relevance_index,
                non_related_project_searches_index,
                force_process=force_process,
            ):
                territories_to_process.append(branch)

        # If no territories to process initially, skip the project
        if not territories_to_process:
            return 0

        # If search has a specific territory_id, filter territories_to_process to only that territory
        final_territories_to_send = territories_to_process
        if search["territory_id"]:
            target_territory_id = search["territory_id"]
            final_territories_to_send = [
                branch
                for branch in territories_to_process
                if branch["territory_id"] == target_territory_id
            ]

            # If the specific territory is not in the list of processable territories for this project, skip
            if not final_territories_to_send:
                return 0

        # Submit task to process project to queue with territories
        processed_projects_cnt = process_project_with_territories(
            project_id,
            search_id,
            search_product_materials_df,
            creation_time_str,
            final_territories_to_send,
            task_client,
            WORKFLOW_INVOCATION_URL,
            batch_id
        )

        return processed_projects_cnt


def project_search_to_task_queue(
    project_candidates_ls,
    search_id_ls,
    search_product_materials_df, 
    task_client,
    WORKFLOW_INVOCATION_URL,
    bq_client,
    settings,
    FILE_PATH,
    TIME_CREATED,
    bucket,
    batch_id,
    force_process=False,
):
    """Process project candidates and send to task queue if they haven't been processed yet."""
    # Get the processed projects from BigQuery
    project_relevance_index = get_processed_projects(
        settings, FILE_PATH, TIME_CREATED, bq_client, bucket
    )
    # Get non-related project searches
    non_related_project_searches_index = get_non_related_project_searches(
        settings, FILE_PATH, TIME_CREATED, bq_client, bucket
    )

    total_project_search_cnt = 0
    futures = []

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=settings.MAX_WORKERS
    ) as executor:
        for _, project_candidate in project_candidates_ls.iterrows():
            for search in search_id_ls:
                future = executor.submit(
                    process_one_project_search_pair,
                    project_candidate,
                    search,
                    search_product_materials_df, 
                    task_client,
                    WORKFLOW_INVOCATION_URL,
                    project_relevance_index,
                    non_related_project_searches_index,
                    batch_id,
                    force_process=force_process,
                )
                futures.append(future)

    # Wrap as_completed with tqdm for progress bar
    for future in tqdm(
        concurrent.futures.as_completed(futures),
        total=len(futures),
        desc="Processing project-search pairs",
    ):
        try:
            count = future.result()
            total_project_search_cnt += count
        except Exception as e:
            log_error(
                function_name="project_search_to_task_queue",
                log_message=f"Task generation failed: {e}",
                endpoint="send-relevent-project-to-queue",
                error_type=type(e).__name__,
                stack_trace=traceback.format_exc(),
            )

    log_default(
        log_message=f"Finished processing. Total project-search pairs sent to queue: {total_project_search_cnt}",
        json_payload=json.dumps(
            {
                "filename": FILE_PATH,
                "time_created": TIME_CREATED,
                "total_project_search_cnt": total_project_search_cnt,
            }
        ),
    )

    return total_project_search_cnt


def process_project_without_territory(
    project_id,
    search_id,
    search_product_materials_df, 
    creation_time,
    task_client,
    workflow_url,
    batch_id
):
    """Process a project without territory and send to task queue."""
    creation_time = creation_time.isoformat(timespec='seconds')
    log_default(
        log_message=f"Sending project to the queue with project_id: {project_id}",
        json_payload=json.dumps(
            {
                "project_id": project_id,
                "search_id": search_id,
                "time_created": creation_time,
                "territory_id": None,
            }
        ),
    )

    # Filter search_materials_df for the  search_id
    search_product_materials_relevant = search_product_materials_df[search_product_materials_df['fbm_searchid'] == search_id] 
    search_product_materials_relevant.reset_index(drop=True, inplace=True)

    # Convert the relevant search materials to JSON
    search_materials_json = search_product_materials_relevant.to_json()

    message = {
        "project_id": project_id,
        "time_created": creation_time,
        "search_id": search_id,
        "territory_id": [{"territory_id": None, "distance_from_territory": None}],
        "distance_from_territory": None,
        "territory_idx": None,
        "search_materials_json": search_materials_json,
        "materials_valuation": None, 
        "assign_queue": "send_project_to_queue",
        "request_type": None,
        "batch_id": batch_id,
    }

    task_client.create_task(url=workflow_url, payload=message)

    return 1


def process_project_with_territories(
    project_id,
    search_id,
    search_product_materials_df, 
    creation_time,
    territories,
    task_client,
    workflow_url,
    batch_id
):
    creation_time = creation_time.isoformat(timespec='seconds')
    territories = [
        {
            "territory_id": branch["territory_id"],
            "distance_from_territory": branch["distance"],
        }
        for branch in territories
    ]
    """Process a project with territories and send to task queue."""
    log_default(
        log_message=f"Sending project to the queue with project_id: {project_id} and search_id: {search_id}",
        json_payload=json.dumps(
            {
                "project_id": project_id,
                "search_id": search_id,
                "time_created": creation_time,
                "territory_id": territories,
            }
        ),
    )

    # Filter search_materials_df for the  search_id
    search_product_materials_df = search_product_materials_df[search_product_materials_df['fbm_searchid'] == search_id] 
    search_product_materials_df.reset_index(drop=True, inplace=True)

    # Convert the relevant search materials to JSON
    search_materials_json = search_product_materials_df.to_json()

    message = {
        "project_id": project_id,
        "time_created": creation_time,
        "search_id": search_id,
        "territory_id": territories,
        "distance_from_territory": None,
        "territory_idx": None,
        "search_materials_json": search_materials_json,
        "materials_valuation": None, 
        "assign_queue": "send_project_to_queue",
        "request_type": None,
        "batch_id": batch_id
    }

    task_client.create_task(url=workflow_url, payload=message)

    return 1
    


PROJECT_CANDIDATES_QUERY = """
WITH new_records AS (
    SELECT
        Details_Detail_Scope,
        Details_Detail_Notes,
        Details_Detail_Details,
        Materials_Material,
        RSMeansMaterialDivisions_Division_Metals,
        RSMeansMaterialDivisions_Division_ThermalandMoistureProtection,
        RSMeansMaterialDivisions_Division_Openings,
        RSMeansMaterialDivisions_Division_Finishes,
        RSMeansMaterialDivisions_Division_Masonry,
        ParentCategories_ParentCategory,
        ParentCategories_PrimaryCategoryName,
        ProjectID,
        Title,
        Stage,
        Valuation_Value,
        DATE(Parameters_Parameter_BidDate) Parameters_Parameter_BidDate,
        Parameters_Parameter_BidTime,
        Parameters_Parameter_WorkType,
        `Addresses_Address`[SAFE_OFFSET(0)].Longitude AS Longitude,
        `Addresses_Address`[SAFE_OFFSET(0)].Latitude AS Latitude,
        -- Add the properly parsed date column here.  This is *critical* for performance.
        PARSE_DATE('%Y%m%d', REGEXP_EXTRACT(sourceFile, r'(\\d{{8}})')) AS sourceFileDate,
        sourceFileCreationTime,
        sourceFile
    FROM `{project}.{dataset}.{cc_table}`
    WHERE sourceFile = '{sourceFile}'
      AND ProjectID NOT IN (
          SELECT ProjectID
          FROM `{project}.{dataset}.{cc_table}`
          WHERE sourceFileCreationTime  > '{source_file_time_created}'
          AND sourceFile != '{sourceFile}'
      )
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

),
old_records AS (
    SELECT
        ProjectID,
        stage,
        Valuation_Value,
        Details_Detail_Scope,
        Details_Detail_Notes,
        Details_Detail_Details,
        ParentCategories_PrimaryCategoryName,
        ParentCategories_ParentCategory,
        Materials_Material,
        RSMeansMaterialDivisions_Division_Metals,
        RSMeansMaterialDivisions_Division_ThermalandMoistureProtection,
        RSMeansMaterialDivisions_Division_Openings,
        RSMeansMaterialDivisions_Division_Finishes,
        RSMeansMaterialDivisions_Division_Masonry,
        `Addresses_Address`[SAFE_OFFSET(0)].Longitude AS Longitude,
        `Addresses_Address`[SAFE_OFFSET(0)].Latitude AS Latitude,
        PARSE_DATE('%Y%m%d', REGEXP_EXTRACT(sourceFile, r'(\\d{{8}})')) AS sourceFileDate  -- Use parsed date here too.
    FROM `{project}.{dataset}.{cc_table}`
    WHERE ProjectID IN (SELECT ProjectID FROM new_records)
      AND sourceFileCreationTime  < '{source_file_time_created}'
      AND sourceFile != '{sourceFile}'
    QUALIFY ROW_NUMBER() OVER (PARTITION BY ProjectID ORDER BY sourceFileDate DESC, UpdateDate DESC) = 1  -- Use the date column
),

-- CTEs to check for differences in array elements *without* string concatenation.
-- These use EXCEPT DISTINCT to find differences.
scope_changes AS (
  SELECT n.ProjectID,
         (SELECT COUNT(*) FROM (
             (SELECT scope_item FROM UNNEST(n.Details_Detail_Scope) AS scope_item EXCEPT DISTINCT SELECT scope_item FROM UNNEST(o.Details_Detail_Scope) AS scope_item)
             UNION ALL
             (SELECT scope_item FROM UNNEST(o.Details_Detail_Scope) AS scope_item EXCEPT DISTINCT SELECT scope_item FROM UNNEST(n.Details_Detail_Scope) AS scope_item)
          )) > 0 AS scope_changed
  FROM new_records_filter n
  LEFT JOIN old_records o ON n.ProjectID = o.ProjectID
),
notes_changes AS (
    SELECT n.ProjectID,
           (SELECT COUNT(*) FROM (
               (SELECT note FROM UNNEST(n.Details_Detail_Notes) AS note EXCEPT DISTINCT SELECT note FROM UNNEST(o.Details_Detail_Notes) AS note)
               UNION ALL
               (SELECT note FROM UNNEST(o.Details_Detail_Notes) AS note EXCEPT DISTINCT SELECT note FROM UNNEST(n.Details_Detail_Notes) AS note)
           )) > 0 AS notes_changed
    FROM new_records_filter n
    LEFT JOIN old_records o ON n.ProjectID = o.ProjectID
),
details_changes AS (
  SELECT n.ProjectID,
         (SELECT COUNT(*) FROM (
             (SELECT detail FROM UNNEST(n.Details_Detail_Details) AS detail EXCEPT DISTINCT SELECT detail FROM UNNEST(o.Details_Detail_Details) AS detail)
             UNION ALL
             (SELECT detail FROM UNNEST(o.Details_Detail_Details) AS detail EXCEPT DISTINCT SELECT detail FROM UNNEST(n.Details_Detail_Details) AS detail)
          )) > 0 AS details_changed
  FROM new_records_filter n
  LEFT JOIN old_records o ON n.ProjectID = o.ProjectID
),
materials_changes AS (
  SELECT n.ProjectID,
         (SELECT COUNT(*) FROM (
             (SELECT CONCAT(m.code, '-', m._) FROM UNNEST(n.Materials_Material) AS m EXCEPT DISTINCT SELECT CONCAT(m.code, '-', m._) FROM UNNEST(o.Materials_Material) AS m)
             UNION ALL
             (SELECT CONCAT(m.code, '-', m._) FROM UNNEST(o.Materials_Material) AS m EXCEPT DISTINCT SELECT CONCAT(m.code, '-', m._) FROM UNNEST(n.Materials_Material) AS m)
          )) > 0 AS materials_changed
  FROM new_records_filter n
  LEFT JOIN old_records o ON n.ProjectID = o.ProjectID
),

rsmeans_metals_changes AS (
    SELECT n.ProjectID,
           (SELECT COUNT(*) FROM (
               (SELECT CONCAT(m.code, '-', m.InstallationCostValue, '-', m.TotalCostValue, '-', m._) FROM UNNEST(n.RSMeansMaterialDivisions_Division_Metals) m EXCEPT DISTINCT SELECT CONCAT(m.code, '-', m.InstallationCostValue, '-', m.TotalCostValue, '-', m._) FROM UNNEST(o.RSMeansMaterialDivisions_Division_Metals) m)
               UNION ALL
               (SELECT CONCAT(m.code, '-', m.InstallationCostValue, '-', m.TotalCostValue, '-', m._) FROM UNNEST(o.RSMeansMaterialDivisions_Division_Metals) m EXCEPT DISTINCT SELECT CONCAT(m.code, '-', m.InstallationCostValue, '-', m.TotalCostValue, '-', m._) FROM UNNEST(n.RSMeansMaterialDivisions_Division_Metals) m)
            )) > 0 AS rsmeans_metals_changed

    FROM new_records_filter n
             LEFT JOIN old_records o ON n.projectID = o.projectID
),

rsmeans_tmp_changes AS (
        SELECT n.projectID,
            (
                SELECT count(*)
                FROM
                (
                    (SELECT CONCAT(m.code, '-', m.InstallationCostValue, '-', m.TotalCostValue, '-', m._) FROM unnest(n.RSMeansMaterialDivisions_Division_ThermalandMoistureProtection) m EXCEPT DISTINCT SELECT CONCAT(m.code, '-', m.InstallationCostValue, '-', m.TotalCostValue, '-', m._) from unnest(o.RSMeansMaterialDivisions_Division_ThermalandMoistureProtection) m)
                    UNION ALL
                    (SELECT CONCAT(m.code, '-', m.InstallationCostValue, '-', m.TotalCostValue, '-', m._) FROM unnest(o.RSMeansMaterialDivisions_Division_ThermalandMoistureProtection) m EXCEPT DISTINCT SELECT CONCAT(m.code, '-', m.InstallationCostValue, '-', m.TotalCostValue, '-', m._) from unnest(n.RSMeansMaterialDivisions_Division_ThermalandMoistureProtection) m)
                )
            ) > 0 as rsmeans_tmp_changed

        FROM new_records_filter n
        LEFT JOIN old_records o ON n.projectID = o.projectID
),

rsmeans_openings_changes AS (
    SELECT n.projectID,
        (
            SELECT count(*)
            FROM
            (
                (SELECT CONCAT(m.code, '-', m.InstallationCostValue, '-', m.TotalCostValue, '-', m._) FROM unnest(n.RSMeansMaterialDivisions_Division_Openings) m EXCEPT DISTINCT SELECT CONCAT(m.code, '-', m.InstallationCostValue, '-', m.TotalCostValue, '-', m._) from unnest(o.RSMeansMaterialDivisions_Division_Openings) m)
                UNION ALL
                (SELECT CONCAT(m.code, '-', m.InstallationCostValue, '-', m.TotalCostValue, '-', m._) FROM unnest(o.RSMeansMaterialDivisions_Division_Openings) m EXCEPT DISTINCT SELECT CONCAT(m.code, '-', m.InstallationCostValue, '-', m.TotalCostValue, '-', m._) from unnest(n.RSMeansMaterialDivisions_Division_Openings) m)
            )
        ) > 0 as rsmeans_openings_changed

    FROM new_records_filter n
    LEFT JOIN old_records o ON n.projectID = o.projectID
),

rsmeans_finishes_changes AS (
    SELECT n.projectID,
        (
            SELECT count(*)
            FROM
            (
                (SELECT CONCAT(m.code, '-', m.InstallationCostValue, '-', m.TotalCostValue, '-', m._) FROM unnest(n.RSMeansMaterialDivisions_Division_Finishes) m EXCEPT DISTINCT SELECT CONCAT(m.code, '-', m.InstallationCostValue, '-', m.TotalCostValue, '-', m._) from unnest(o.RSMeansMaterialDivisions_Division_Finishes) m)
                UNION ALL
                (SELECT CONCAT(m.code, '-', m.InstallationCostValue, '-', m.TotalCostValue, '-', m._) FROM unnest(o.RSMeansMaterialDivisions_Division_Finishes) m EXCEPT DISTINCT SELECT CONCAT(m.code, '-', m.InstallationCostValue, '-', m.TotalCostValue, '-', m._) from unnest(n.RSMeansMaterialDivisions_Division_Finishes) m)
            )
        ) > 0 as rsmeans_finishes_changed
    FROM new_records_filter n
    LEFT JOIN old_records o ON n.projectID = o.projectID
),

rsmeans_masonry_changes AS (
     SELECT n.projectID,
        (
            SELECT count(*)
            FROM
            (
                (SELECT CONCAT(m.code, '-', m.InstallationCostValue, '-', m.TotalCostValue, '-', m._) FROM unnest(n.RSMeansMaterialDivisions_Division_Masonry) m EXCEPT DISTINCT SELECT CONCAT(m.code, '-', m.InstallationCostValue, '-', m.TotalCostValue, '-', m._) from unnest(o.RSMeansMaterialDivisions_Division_Masonry) m)
                UNION ALL
                (SELECT CONCAT(m.code, '-', m.InstallationCostValue, '-', m.TotalCostValue, '-', m._) FROM unnest(o.RSMeansMaterialDivisions_Division_Masonry) m EXCEPT DISTINCT SELECT CONCAT(m.code, '-', m.InstallationCostValue, '-', m.TotalCostValue, '-', m._) from unnest(n.RSMeansMaterialDivisions_Division_Masonry) m)
            )
        ) > 0 as rsmeans_masonry_changed
    FROM new_records_filter n
    LEFT JOIN old_records o ON n.projectID = o.projectID
),
parent_category_changes AS (
    SELECT
        n.ProjectID,
        (SELECT COUNT(*) FROM (
            (SELECT pc.Name, subcategory
             FROM UNNEST(n.ParentCategories_ParentCategory) AS pc, UNNEST(pc.SubCategories.SubCategory) AS subcategory
             EXCEPT DISTINCT
             SELECT pc.Name, subcategory
             FROM UNNEST(o.ParentCategories_ParentCategory) AS pc, UNNEST(pc.SubCategories.SubCategory) AS subcategory)
            UNION ALL
            (SELECT pc.Name, subcategory
             FROM UNNEST(o.ParentCategories_ParentCategory) AS pc, UNNEST(pc.SubCategories.SubCategory) AS subcategory
             EXCEPT DISTINCT
             SELECT pc.Name, subcategory
             FROM UNNEST(n.ParentCategories_ParentCategory) AS pc, UNNEST(pc.SubCategories.SubCategory) AS subcategory)
        )) > 0 AS parent_category_changed
    FROM new_records_filter n
    LEFT JOIN old_records o ON n.ProjectID = o.ProjectID

),
batchId AS (
  select GENERATE_UUID() batch_id
),
OwnerName AS (
                SELECT
                    ProjectID,
                    company.role As role,
                    company.Name AS owner_name,
                FROM (select ProjectID,Companies from `{project}.{dataset}.{cc_table}`
                WHERE Date(sourceFileCreationTime) >=  DATE(DATETIME_SUB(CURRENT_DATETIME(), INTERVAL 30 DAY))
                    {sourceFilefilter}),
                    UNNEST(Companies) AS company_wrap,
                    UNNEST(company_wrap.Company) AS company
                where lower(company.role ) = "owner"
                qualify ROW_number() OVER(PARTITION BY ProjectID ) =1
            )

SELECT
    batch_id,
    n.ProjectID as project_id,
    n.title as ProjectTitle,
    CAST(n.Valuation_Value AS FLOAT64) as Valuation,
    n.Stage,
    n.Longitude as long,
    n.Latitude as lat,
    n.Parameters_Parameter_BidDate as BidDate,
    n.Parameters_Parameter_BidTime as BidTime,
    n.Parameters_Parameter_WorkType as WorkType,
    n.ParentCategories_PrimaryCategoryName as PrimaryCategoryName,
    n.sourceFile, 
    n.sourceFileCreationTime,
    OwnerName.owner_name as owner_name,
    "construct_connect" as data_source 
FROM new_records_filter n
LEFT JOIN old_records o ON n.ProjectID = o.ProjectID
LEFT JOIN scope_changes sc ON n.ProjectID = sc.ProjectID
LEFT JOIN notes_changes nc ON n.ProjectID = nc.ProjectID
LEFT JOIN details_changes dc ON n.ProjectID = dc.ProjectID
LEFT JOIN materials_changes mc ON n.ProjectID = mc.ProjectID
LEFT JOIN rsmeans_metals_changes rmet ON n.ProjectID = rmet.ProjectID
LEFT JOIN rsmeans_tmp_changes rtmp ON n.projectID = rtmp.projectID
LEFT JOIN rsmeans_openings_changes ro ON n.projectID = ro.projectID
LEFT JOIN rsmeans_finishes_changes rf ON n.ProjectID = rf.projectID
LEFT JOIN rsmeans_masonry_changes rmason ON n.projectID = rmason.projectID
LEFT JOIN parent_category_changes pcc ON n.ProjectID = pcc.ProjectID
LEFT JOIN OwnerName ON n.ProjectID = OwnerName.ProjectID
,batchId
WHERE
    o.ProjectID IS NULL  -- Include new records with no old record.
    OR COALESCE(n.Stage, '') != COALESCE(o.Stage, '')
    OR COALESCE(CAST(n.Valuation_Value AS FLOAT64), 0) != COALESCE(CAST(o.Valuation_Value AS FLOAT64), 0)
    OR COALESCE(n.ParentCategories_PrimaryCategoryName, '') != COALESCE(o.ParentCategories_PrimaryCategoryName, '')
    OR pcc.parent_category_changed
    OR sc.scope_changed
    OR nc.notes_changed
    OR dc.details_changed
    OR mc.materials_changed
    OR rmet.rsmeans_metals_changed
    OR rtmp.rsmeans_tmp_changed
    OR ro.rsmeans_openings_changed
    OR rf.rsmeans_finishes_changed
    OR rmason.rsmeans_masonry_changed
;"""

DODGE_PROJECT_CANDIDATES_QUERY = """ 
WITH new_records AS (
    SELECT
      *
    FROM `{project}.{dataset}.{dd_table}`
    WHERE sourceFile = '{sourceFile}'
      AND DRNumber NOT IN (
          SELECT DRNumber
          FROM `{project}.{dataset}.{dd_table}`
          WHERE sourceFileCreationTime  > '{source_file_time_created}'
          AND sourceFile != '{sourceFile}'
      )
),
new_records_filter AS (
    SELECT nr.*
    FROM new_records nr
    WHERE
        CAST(nr.Valuation AS FLOAT64) >= 1000000
        AND nr.BidDate IS NOT NULL
        AND nr.PrimaryStage NOT IN ('Abandoned',  'Construction Documents',  'Design Development', 'Notice of Completion',  'Planning Schematics', 'Pre-Design', 'Pre-Qualification', 'Request for Qualifications')
        -- Have to filter out not relevant materials and categories

),
old_records AS (
    SELECT
        *
    FROM `{project}.{dataset}.{dd_table}`
    WHERE DRNumber IN (SELECT DRNumber FROM new_records)
      AND sourceFileCreationTime  < '{source_file_time_created}'
      AND sourceFile != '{sourceFile}'
    QUALIFY ROW_NUMBER() OVER (PARTITION BY DRNumber ORDER BY VersionNumber DESC) = 1 
),
batchId as(
  select GENERATE_UUID() batch_id
),
OwnerName AS (
    SELECT
        DRNumber,
        company.FactorType,
        company.CompanyName AS owner_name,
    FROM (select DRNumber,Companies from `{project}.{dataset}.{dd_table}`
    WHERE Date(sourceFileCreationTime) >=  DATE(DATETIME_SUB(CURRENT_DATETIME(), INTERVAL 30 DAY))
    {sourceFilefilter}),
        UNNEST(Companies.company) AS company
    where lower(company.FactorType)  = "owner"
    qualify ROW_number() OVER(PARTITION BY DRNumber ) =1
)

SELECT
    batch_id,
    n.DRNumber as project_id,
    n.ProjectTitle,
    cast(n.valuation as float64) as Valuation,
    n.PrimaryStage as stage,
    cast(n.Lat as Numeric) as Lat,
    cast(n.Long as Numeric) as Long,
    n.Biddate,
    n.BidTime,
    n.TypeOfWork as WorkType,
    n.PrimaryProjectType as PrimaryCategoryName,
    n.sourceFile,
    n.sourceFileCreationTime,
    OwnerName.owner_name as owner_name,
    'dodge' as data_source
FROM new_records_filter n
LEFT JOIN old_records o ON n.DRNumber = o.DRNumber
LEFT JOIN OwnerName ON n.DRNumber = OwnerName.DRNumber

,batchId
WHERE
    o.DRNumber IS NULL  -- Include new records with no old record.
    OR COALESCE(n.PrimaryStage, '') != COALESCE(o.PrimaryStage, '')
    OR COALESCE(CAST(n.Valuation AS FLOAT64), 0) != COALESCE(CAST(o.Valuation AS FLOAT64), 0)
    OR COALESCE(n.MarketSegment, '') != COALESCE(o.MarketSegment, '')
    OR COALESCE(n.PrimaryProjectType, '') != COALESCE(o.PrimaryProjectType, '')
    OR COALESCE(n.StatusText, '') != COALESCE(o.StatusText, '')
    OR COALESCE(n.FeaturesInfo, '') != COALESCE(o.FeaturesInfo, '')
    OR COALESCE(n.OwnershipType, '') != COALESCE(o.OwnershipType, '')
    OR COALESCE(n.TypeOfWork, '') != COALESCE(o.TypeOfWork, '')"""











LAST_30DAYS_PROJECT_CANDIDATES_QUERY = """WITH new_records AS (
    SELECT
        Details_Detail_Scope,
        Details_Detail_Notes,
        Details_Detail_Details,
        Materials_Material,
        RSMeansMaterialDivisions_Division_Metals,
        RSMeansMaterialDivisions_Division_ThermalandMoistureProtection,
        RSMeansMaterialDivisions_Division_Openings,
        RSMeansMaterialDivisions_Division_Finishes,
        RSMeansMaterialDivisions_Division_Masonry,
        ParentCategories_ParentCategory,
        ParentCategories_PrimaryCategoryName,
        ProjectID,
        Stage,
        Valuation_Value,
        Parameters_Parameter_BidDate,
        `Addresses_Address`[SAFE_OFFSET(0)].Longitude AS Longitude,
        `Addresses_Address`[SAFE_OFFSET(0)].Latitude AS Latitude,
        -- Add the properly parsed date column here.  This is *critical* for performance.
        PARSE_DATE('%Y%m%d', REGEXP_EXTRACT(sourceFile, r'(\\d{{8}})')) AS sourceFileDate,
        sourceFileCreationTime
    FROM `{project}.{dataset}.{cc_table}`
    WHERE sourceFile != '{sourceFile}' --Skipping delta records as they have already been processed and sent to the task queue by the previous query.
      AND  sourceFileCreationTime  >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL 30 DAY)
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
    n.ProjectID,
    n.sourceFileCreationTime,
    n.Longitude,
    n.Latitude,
FROM new_records_filter n
;"""
