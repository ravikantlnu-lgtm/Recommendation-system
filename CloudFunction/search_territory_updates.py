import io
import json
import logging
import os
import traceback
from datetime import datetime
import pandas as pd
import pandas_gbq

import functions_framework
from config import get_settings
from logging_config import log_default, log_error
from services import BigQueryManager, DynamicsManager
from utils import (
    NEW_OR_MODIFIED_SEARCH_IDENTIFIER_QUERY,
    UPSERT_SEARCHES_QUERY,
    UPSERT_SEARCHES_TERRITORIES_QUERY,
    UPSERT_TERRITORIES_QUERY,
)
from utils.common import truncate_iso_to_seconds

# Load settings
settings = get_settings()


def create_json_file(data_ls):
    json_file = io.StringIO()
    for search_data in data_ls:
        json_file.write(json.dumps(search_data) + "\n")
    json_file.seek(0)  # Reset file pointer to the beginning
    return json_file


@functions_framework.http
def search_territory_updates(request):
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
    
    try:
        # BigQuery configuration
        project_id = settings.PROJECT_ID
        dataset_id = settings.BIGQUERY_DATASET
        searches_table_id = settings.SEARCHES_TABLE_ID
        searches_staging_table_id = settings.SEARCHES_STAGING_TABLE_ID
        territories_table_id = settings.TERRITORIES_TABLE_ID
        territories_staging_table_id = settings.TERRITORIES_STAGING_TABLE_ID
        search_territory_table_id = settings.SEARCH_TERRITORY_TABLE_ID
        search_territory_staging_table_id = settings.SEARCH_TERRITORY_STAGING_TABLE_ID

        # Dynamics credentials
        dynamics_cred = json.loads(os.getenv("dynamics_cred"))

        # Dynamics configuration
        tenant_id = dynamics_cred["TENANT_ID"]
        application_id = dynamics_cred["APPLICATION_ID"]
        client_secret = dynamics_cred["CLIENT_SECRET"]
        dynamics_instance = settings.DM_INSTANCE_URL

        # Initialize BigQuery client
        bq_client = BigQueryManager(dataset_id=dataset_id)

        bq_client.truncate_table(table_id=searches_staging_table_id)
        bq_client.truncate_table(table_id=territories_staging_table_id)
        bq_client.truncate_table(table_id=search_territory_staging_table_id)

        # Initialize Dynamics client
        dynamics_client = DynamicsManager(
            domain=dynamics_instance,
            client_id=application_id,
            client_secret=client_secret,
        )
        token_result = dynamics_client.build_msal_client(
            tenant_id
        ).acquire_token_for_client([f"{dynamics_instance}/.default"])
        dynamics_client.set_access_token(token_result["access_token"])

        # Fetch data from Dynamics
        log_default(
            log_message=f"Fetching data for search table from Dynamics.",
            json_payload=json.dumps(
                {"filename": FILE_PATH, "timeCreated": timeCreated}
            ),
        )
        entity_name = f"{settings.DM_SEARCH_TABLE_ID}s"
        search_data_response = dynamics_client.get_data(entity_name)
        # Process and prepare data for BigQuery
        search_data_list = []
        for search in search_data_response.get("value", []):
            search_data_list.append(
                {
                    "id": search["fbm_searchid"],
                    "name": search["fbm_name"],
                    "category": str(search["fbm_category"]),
                    "boolean": search["fbm_booleansearch"],
                    "upsert_time": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                }
            )

        # Convert search_data_list to newline-delimited JSON and store in an in-memory file
        search_json_file = create_json_file(search_data_list)
        log_default(
            log_message=f"Loading data into the search staging table.",
            json_payload=json.dumps(
                {"filename": FILE_PATH, "timeCreated": timeCreated}
            ),
        )
        bq_client.load_jsonl_file(
            table_id=searches_staging_table_id, file_content=search_json_file
        )

        new_or_modified_search_identifier_query = (
            NEW_OR_MODIFIED_SEARCH_IDENTIFIER_QUERY.format(
                project_id=project_id,
                dataset_id=dataset_id,
                search_staging_table=searches_staging_table_id,
                search_table=searches_table_id,
            )
        )
        log_default(
            log_message=f"Identifying new or modified searches.",
            json_payload=json.dumps(
                {"filename": FILE_PATH, "timeCreated": timeCreated}
            ),
        )
        new_or_modified_searchs = bq_client.query_table(
            new_or_modified_search_identifier_query
        )

        new_or_modified_searchs = ",".join(
            search["id"] for search in new_or_modified_searchs
        )

        upsert_search_query = UPSERT_SEARCHES_QUERY.format(
            project_id=project_id,
            dataset_id=dataset_id,
            target_table=searches_table_id,
            source_table=searches_staging_table_id,
        )
        log_default(
            log_message=f"Executing the upsert searches query.",
            json_payload=json.dumps(
                {"filename": FILE_PATH, "timeCreated": timeCreated}
            ),
        )
        bq_client.query_table(upsert_search_query)

        # Fetch data from Dynamics
        log_default(
            log_message=f"Fetching data for search_territory_map table from Dynamics.",
            json_payload=json.dumps(
                {"filename": FILE_PATH, "timeCreated": timeCreated}
            ),
        )
        entity_name = f"{settings.DM_SEARCH_TERRITORY_MAP_ID}s"
        search_territory_data_response = dynamics_client.get_data(entity_name)
        # Process and prepare data for BigQuery
        search_territory_data_list = []
        for search_territory in search_territory_data_response.get("value", []):
            search_territory_data_list.append(
                {
                    "territory_id": search_territory["_fbm_branchid_value"],
                    "search_id": search_territory["_fbm_searchid_value"],
                }
            )

        # Convert search_territory_data_list to newline-delimited JSON and store in an in-memory file
        search_territory_file = create_json_file(search_territory_data_list)
        log_default(
            log_message=f"Loading data into the search_territory_map staging table.",
            json_payload=json.dumps(
                {"filename": FILE_PATH, "timeCreated": timeCreated}
            ),
        )
        bq_client.load_jsonl_file(
            table_id=search_territory_staging_table_id,
            file_content=search_territory_file,
        )

        upsert_search_territory_query = UPSERT_SEARCHES_TERRITORIES_QUERY.format(
            project_id=project_id,
            dataset_id=dataset_id,
            target_table=search_territory_table_id,
            source_table=search_territory_staging_table_id,
        )
        log_default(
            log_message=f"Executing the upsert search_territory query.",
            json_payload=json.dumps(
                {"filename": FILE_PATH, "timeCreated": timeCreated}
            ),
        )
        bq_client.query_table(upsert_search_territory_query)

        # Fetch data from Dynamics
        log_default(
            log_message=f"Fetching data for territories table from Dynamics.",
            json_payload=json.dumps(
                {"filename": FILE_PATH, "timeCreated": timeCreated}
            ),
        )
        entity_name = f"{settings.DM_TERRITORY_TABLE_ID}s"
        territories_data_response = dynamics_client.get_data(entity_name)
        # Process and prepare data for BigQuery
        territories_data_list = []
        for territories in territories_data_response.get("value", []):
            territories_data_list.append(
                {
                    "id": territories["teamid"],
                    "name": territories["name"],
                    "latitude": territories["fbm_latitude"],
                    "longitude": territories["fbm_longitude"],
                    "upsert_time": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                }
            )

        # Convert search_data_list to newline-delimited JSON and store in an in-memory file
        territories_json_file = create_json_file(territories_data_list)
        log_default(
            log_message=f"Loading data into the territories staging table.",
            json_payload=json.dumps(
                {"filename": FILE_PATH, "timeCreated": timeCreated}
            ),
        )
        bq_client.load_jsonl_file(
            table_id=territories_staging_table_id, file_content=territories_json_file
        )

        upsert_territories_query = UPSERT_TERRITORIES_QUERY.format(
            project_id=project_id,
            dataset_id=dataset_id,
            target_table=territories_table_id,
            source_table=territories_staging_table_id,
        )
        log_default(
            log_message=f"Executing the upsert territories query.",
            json_payload=json.dumps(
                {"filename": FILE_PATH, "timeCreated": timeCreated}
            ),
        )
        bq_client.query_table(upsert_territories_query)


        log_default(
            log_message=f"Fetching data for search_product_category_map table from Dynamics.",
            json_payload=json.dumps(
                {"filename": FILE_PATH, "timeCreated": timeCreated}
            ),
        )
        
        # Fetch data from Dynamics
        entity_name = f"{settings.DM_PROFILE_CATEGORIES_ID}"
        profile_categories_df = pd.DataFrame(dynamics_client.get_data(entity_name)['value'])

        entity_name = f"{settings.DM_PRODUCT_CATEGORIES_ID}" 
        product_categories_df = pd.DataFrame(dynamics_client.get_data(entity_name)['value'])

        if profile_categories_df.empty or product_categories_df.empty: 
            search_product_category_df = pd.DataFrame()
        else: 
            # Merge data and drop null values
            search_product_category_df = profile_categories_df.merge(product_categories_df, on='fbm_productcategoryid', how='left')
            search_product_category_df = search_product_category_df[['fbm_searchid', 'fbm_productcategoryid', 'fbm_productcatcode']]
            search_product_category_df = search_product_category_df.dropna()

        pandas_gbq.to_gbq(
            search_product_category_df,
            destination_table=f"{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.{settings.SEARCH_PRODUCT_CATEGORY_MAP_TABLE_ID}",
            project_id=settings.PROJECT_ID,
            if_exists="replace",
        )


        return {
            "status": "success",
            "log_message": "Tables synced successfully.",
            "new_or_modified_searchs": new_or_modified_searchs,
            "filename": FILE_PATH,
            "timeCreated": timeCreated,
        }
    except Exception as e:
        stack_trace = traceback.format_exc()
        log_error(
            function_name="search_territory_updates_cloud_function",
            endpoint="search_territory_updates",
            log_message=str(e),
            error_type=type(e).__name__,
            stack_trace=stack_trace,
            json_payload=json.dumps(
                {"filename": FILE_PATH, "timeCreated": timeCreated}
            ),
        )
        return {
            "status": "failed",
            "log_message": str(e),
            "error_type": type(e).__name__,
            "stack_trace": stack_trace,
            "filename": FILE_PATH,
            "timeCreated": timeCreated,
        }
