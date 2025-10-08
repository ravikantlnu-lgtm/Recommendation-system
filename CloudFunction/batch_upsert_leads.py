import json
import logging
import os
import time
import traceback
import uuid
import numpy as np
import pandas as pd
from collections import defaultdict
from datetime import datetime, timezone
import concurrent.futures

import functions_framework
import requests
from config import get_settings
from logging_config import log_default, log_error
from services import BigQueryManager, DynamicsManager
from utils.common import get_secret, invoke_cloud_function, truncate_iso_to_seconds
from utils.batch_upsert_leads_utils import (
    CREATE_UNIQUE_COMBINATION_QUERY, 
    fetch_sales_rep_info,
    process_batches_concurrently,
    get_existing_branchopportunity,
    separate_update_insert_branchopportunity,
    get_relevance_code,
    build_batch_opportunities,
    _load_batch_upsert_lead_table,
    get_project_details,
    get_source_code,
    add_bullets,
    push_consolidated_data,
)

from tqdm import tqdm
from google.cloud import bigquery

settings = get_settings()


big_query_client = BigQueryManager(dataset_id=settings.BIGQUERY_DATASET)


def get_dynamics_client():
    dynamics_cred = get_secret(
        project_number=settings.PROJECT_NUMBER, secret_name="dynamics_cred"
    )
    dynamics_cred = json.loads(dynamics_cred)

    # Dynamics configuration
    tenant_id = dynamics_cred["TENANT_ID"]
    application_id = dynamics_cred["APPLICATION_ID"]
    client_secret = dynamics_cred["CLIENT_SECRET"]
    dynamics_instance = settings.DM_INSTANCE_URL

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

    return dynamics_client



# def get_state_name(state_province:str):
def get_state_name(state_province: str):
    """
    Converts a state to its full name.
    This function takes a two-letter abbreviation of a U.S. state or Canadian province
    and returns the corresponding full name. If the abbreviation is not found in the
    predefined dictionary, the input abbreviation is returned as-is.
    """

    states_name_dict = {
        # United States
        "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
        "CA": "California", "CO": "Colorado", "CT": "Connecticut", 
        "DC":"District of Columbia","DE": "Delaware",
        "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
        "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
        "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
        "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
        "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
        "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
        "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
        "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
        "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
        "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
        "WI": "Wisconsin", "WY": "Wyoming",

        # Canada
        "AB": "Alberta", "BC": "British Columbia", "MB": "Manitoba", "NB": "New Brunswick", "NF": "Newfoundland",
        "NL": "Newfoundland and Labrador", "NS": "Nova Scotia", "NT": "Northwest Territories",
        "NU": "Nunavut", "ON": "Ontario", "PE": "Prince Edward Island",
        "QC": "Quebec", "SK": "Saskatchewan", "YT": "Yukon"
    }
    return states_name_dict.get(state_province.upper(),state_province)


def build_batch_insert_data(
    insert_leads,
    project_relevance_data_map,
    external_lead_dict: dict,
    confidence_threshold: float = None,
):
    batch_data = []
    for record in insert_leads:
        data = {}
        pr = project_relevance_data_map.get((record["project_id"], record["search_id"]))
        new_leadid = uuid.uuid4()
        
        try:
            external_lead_id= external_lead_dict[record["project_id"]]
        except:
            raise ValueError(f"External lead ID not found for project {record['project_id']}")
        data = {
            "leadid": str(new_leadid),
            "fbm_searchid@odata.bind": f"/fbm_searchs({pr['search_id']})",
            "fbm_relevancereasoning": add_bullets(pr["reasoning"][:3000]),
            "fbm_distance": pr["distance"],
            "fbm_externalleadidlookup@odata.bind": f"/fbm_externalleads({external_lead_id})"
            # "ownerid@odata.bind": f"/systemusers({record['sales_rep_id']})"
        }

        # Set the relevance based on confidence score
        confidence_score = pr.get("confidence", None)
        if (
            confidence_score
            and confidence_threshold
            and confidence_score < confidence_threshold
        ):
            relevance = "unsure"
        else:
            relevance = pr["relevance"]

        data["fbm_relevance"] = get_relevance_code(relevance)

        # If sales_rep_id is the default ID, refer to the teams table; otherwise, refer to the systemuser table.
        if record["sales_rep_id"] == settings.DM_DEFAULT_SALES_REP_ID.strip():
            data["ownerid@odata.bind"] = f"/teams({record['sales_rep_id']})"
        else:
            data["ownerid@odata.bind"] = f"/systemusers({record['sales_rep_id']})"

        if pr["territory_id"] is not None:
            data["fbm_branch@odata.bind"] = f"/teams({pr['territory_id']})"

        for attributes in record["project_details"].keys():
            if record["project_details"][attributes]:
                if attributes == "arb_leadsourcecode":
                    data["arb_leadsourcecode"] = get_source_code(record['project_details']['arb_leadsourcecode'])
                else:
                    data[attributes] = record["project_details"][attributes]


        # Get full name of arb_project_stateorprovince
        if data.get("arb_project_country") in ["UNITED STATES","CANADA"]:
            state_code = data.get("arb_project_stateorprovince")
            data["arb_project_stateorprovince"] = get_state_name(state_code)
        batch_data.append(data)
    return batch_data


def build_batch_update_data(
    update_leads, 
    project_relevance_data_map,  
    external_lead_dict: dict, 
    confidence_threshold: float = None
):
    batch_data = []
    for record in update_leads:
        pr = project_relevance_data_map.get((record["project_id"], record["search_id"]))

        existing_time = datetime.fromisoformat(
            record["crm_data"]["fbm_lastsyncdate"].replace("Z", "+00:00")
        ).replace(microsecond=0, tzinfo=timezone.utc)
        input_time = datetime.fromisoformat(
            record["project_details"]["fbm_lastsyncdate"].replace("Z", "+00:00")
        ).replace(microsecond=0, tzinfo=timezone.utc)

        should_update = False

        distance_from_territory = pr.get("distance")
        existing_distance = record["crm_data"].get("fbm_distance")
        # Determine update strategy based on distance and time
        if distance_from_territory is None or existing_distance is None:
            should_update = input_time >= existing_time
        elif distance_from_territory <= existing_distance:
            should_update = input_time >= existing_time
        else:  # distance_from_territory > existing_distance
            should_update = input_time >= existing_time

        # Perform the appropriate update
        if should_update:
            try:
                external_lead_id= external_lead_dict[record["project_id"]]
            except:
                raise ValueError(f"External lead ID not found for project ->{record['project_id']}")
            
            data = {
                "leadid": record["crm_data"]["leadid"],
                "fbm_relevancereasoning": add_bullets(pr["reasoning"][:3000]),
                "fbm_distance": pr["distance"],
                "fbm_externalleadidlookup@odata.bind": f"/fbm_externalleads({external_lead_id})"
            }

            # Set the relevance based on confidence score
            confidence_score = pr.get("confidence", None)
            if (
                confidence_score
                and confidence_threshold
                and confidence_score < confidence_threshold
            ):
                relevance = "unsure"
            else:
                relevance = pr["relevance"]

            data["fbm_relevance"] = get_relevance_code(relevance)

            if pr["territory_id"] is not None:
                data["fbm_branch@odata.bind"] = f"/teams({pr['territory_id']})"
            for attributes in record["project_details"].keys():
                if record["project_details"][attributes]:
                    if attributes == "arb_leadsourcecode":
                        data["arb_leadsourcecode"] = get_source_code(record['project_details']['arb_leadsourcecode'])
                    else:
                        data[attributes] = record["project_details"][attributes]

            # Get full name of arb_project_stateorprovince
            if data.get("arb_project_country") in ["UNITED STATES","CANADA"]:
                state_code = data.get("arb_project_stateorprovince")
                data["arb_project_stateorprovince"] = get_state_name(state_code)
            
            batch_data.append(data)
    return batch_data


def separate_update_insert(already_exists_leads, unique_combinations, project_details_index):
    """Separate leads into insert and update lists based on existing data"""
    insert_leads, update_leads = [], []

    for uc in unique_combinations:
        key = (uc["project_id"], uc["search_id"], uc["sales_rep_id"])
        project_details = project_details_index.get(uc["project_id"])

        record = {
            "project_id": uc["project_id"],
            "search_id": uc["search_id"],
            "sales_rep_id": uc["sales_rep_id"],
            "project_details": project_details,
        }

        if key in already_exists_leads:
            record["crm_data"] = already_exists_leads[key]
            update_leads.append(record)
        else:
            insert_leads.append(record)

    return insert_leads, update_leads


def get_existing_lead_data(
    dynamics_client: DynamicsManager, 
    unique_combinations: list, 
    settings,
    chunck_size: int = 100
):
    """Get existing lead data from Dynamics CRM"""

    def get_leads(combinations):
        filter_ls = []
        for uc in combinations:
            filter_ls.append(
                f"""(fbm_externalleadid eq '{uc.get("project_id")}' and _fbm_searchid_value eq {uc.get("search_id")} and _ownerid_value eq {uc.get("sales_rep_id")})"""
            )

        filter_by = " or ".join(filter_ls)

        select_by = ["leadid", "fbm_externalleadid", "_fbm_searchid_value", "_ownerid_value", "fbm_distance", "fbm_lastsyncdate"]
        
        query_params = {"$filter": filter_by, "$select": ",".join(select_by)}

        url = f"{dynamics_client.domain}/{dynamics_client.api_path}/{settings.DM_LEAD_ID}s"
        headers = dynamics_client.headers
        try:
            response = requests.get(url, headers=headers, params=query_params)
            response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
            response = response.json()
        except requests.exceptions.RequestException as e:
            if "response" in locals() and response is not None:
                raise requests.exceptions.RequestException(
                    f"GET Request Error: {e}\n"
                    f"Response status code: {response.status_code}\n"
                    f"Response body: {response.text if response.content else 'No content'}"
                )
            raise requests.exceptions.RequestException(f"GET Request Error: {e}\n")

        already_exists_leads = {}
        for lead in response["value"]:
            _ownerid_value = lead["_ownerid_value"]
            fbm_externalleadid = lead["fbm_externalleadid"]
            _fbm_searchid_value = lead["_fbm_searchid_value"]
            leadid = lead["leadid"]

            key = (fbm_externalleadid, _fbm_searchid_value, _ownerid_value)
            already_exists_leads[key] = {
                "leadid": leadid,
                "fbm_distance": lead["fbm_distance"],
                "fbm_lastsyncdate": lead["fbm_lastsyncdate"],
            }

        return already_exists_leads

    already_exists_leads = {}

    for i in range(0, len(unique_combinations), chunck_size):
        chunk = unique_combinations[i : i + chunck_size]
        already_exists_leads |= get_leads(chunk )

    return already_exists_leads

def get_unique_combinations(
    settings,
    dynamics_client,
    project_relevance_data,
):
    defult_sales_rep_id = (
        settings.DM_DEFAULT_SALES_REP_ID if settings.DM_DEFAULT_SALES_REP_ID else None
    )

    sales_profile_map = defaultdict(set)
    sales_profile_without_territory_map = defaultdict(set)  # Use set for consistency

    sales_profile_data = dynamics_client.get_data(
        f"{settings.DM_SALES_PROFILE_ID}s", paginate=True
    )
    for row in sales_profile_data.get("value", []):
        search_id = str(row["_fbm_searchid_value"])
        owner_id = str(row["_ownerid_value"])
        territory_id = (
            str(row["_fbm_branchid_value"]) if row["_fbm_branchid_value"] else None
        )

        if territory_id is None:
            sales_profile_without_territory_map[search_id].add(owner_id)
        else:
            map_key = (search_id, territory_id)
            sales_profile_map[map_key].add(owner_id)

    unique_combinations_set = set()  # Use a set for efficient uniqueness tracking
    final_combinations_list = []

    for pr_row in project_relevance_data:
        project_id_pr = pr_row.get("project_id")
        search_id_pr = str(pr_row.get("search_id")) if pr_row.get("search_id") else None
        territory_id_pr = (
            str(pr_row.get("territory_id")) if pr_row.get("territory_id") else None
        )
        time_created_pr = pr_row.get("time_created")

        # Skip if essential IDs are missing
        if project_id_pr is None or search_id_pr is None:
            continue

        found_specific_rep = False
        reps_to_add = set()

        # 1. Check for territory-specific reps
        if territory_id_pr:
            specific_reps = sales_profile_map.get((search_id_pr, territory_id_pr))
            if specific_reps:
                reps_to_add.update(specific_reps)
                found_specific_rep = True

        # 2. Check for non-territory reps (Adjust logic based on requirements)
        # Assign if project HAS territory
        if territory_id_pr:
            non_territory_reps = sales_profile_without_territory_map.get(search_id_pr)
            if non_territory_reps:
                reps_to_add.update(non_territory_reps)

        # 3. Assign default rep if no specific reps found
        if not reps_to_add and defult_sales_rep_id:
            reps_to_add.add(defult_sales_rep_id)
        elif not reps_to_add and not defult_sales_rep_id:
            reps_to_add.add(None)  # Explicitly handle no rep case if default is None

        # Create unique combinations for each rep
        for sales_rep_id in reps_to_add:
            combination_key = (project_id_pr, search_id_pr, sales_rep_id)
            if combination_key not in unique_combinations_set:
                unique_combinations_set.add(combination_key)
                final_combinations_list.append(
                    {
                        # Ensure sales_rep_id is consistently a single value (string or None)
                        "sales_rep_id": sales_rep_id,
                        "project_id": project_id_pr,
                        "search_id": search_id_pr,
                        "time_created_pr": time_created_pr,
                        "territory_id": territory_id_pr
                    }
                )

    return final_combinations_list


def create_core_rows(df, settings):
    # Fetch searches from BigQuery
    searches_query = f"""select id, name from `{settings.BIGQUERY_DATASET}.{settings.SEARCHES_TABLE_ID}`"""
    searches_result = big_query_client.query_table(
        query=searches_query, to_dataframe=True
    )
    searches_result = searches_result.rename(columns={"id": "search_id"})

    # Fetch searchID for core
    core_row = searches_result[searches_result["name"].str.lower() == "core"].copy()
    core_search_id = core_row["search_id"].iloc[0]

    # Add search names to the dataframe
    df_with_searches = df.merge(searches_result, how="left", on="search_id")

    # Filter the dataframe to include only relevant searches under Core
    df_relevant_searches = df_with_searches[
        df_with_searches["name"]
        .str.lower()
        .isin(["ceilings", "drywall", "steel sales"])
    ]
    df_relevant_searches = df_relevant_searches.sort_values(by=["project_id"])

    # Add relevance codes
    df_relevant_searches["relevance_code"] = df_relevant_searches["relevance"].apply(
        get_relevance_code
    )

    # Sort DF with min relevance code (highest relevance) and max confidence
    df_relevant_searches = df_relevant_searches.sort_values(
        by=["project_id", "relevance_code", "confidence"], ascending=[True, True, False]
    )

    # Group by project_id and take the first row (which now has min relevance_code, max confidence on tie)
    core_df = df_relevant_searches.loc[
        df_relevant_searches.groupby("project_id").head(1).index
    ]
    core_df["search_id"] = core_search_id

    core_df.drop(columns=["name", "relevance_code"], inplace=True)

    return core_df

def range_incrementer(start: tuple, step: int =2000) -> tuple:
    """
    Increment a range by a specified step.
    This function takes a tuple representing a range (start and end) 
    and increments both values by a given step.
    Returns:
        tuple: A new tuple with both elements incremented by the step value.
    """
    
    return (start[0]+step, start[1]+step )

def invoke_another_instance(
    instance,
    FILE_PATH,
    timeCreated,
    backfill,
    search_ids,
    record_range
):
    """
    Invokes another instance of batch_upsert_leads to handle the timeout limit of the cloud function.
    This ensures that processing continues seamlessly by triggering a new instance with updated parameters.
    """
    log_default(
        log_message=f"Instance {instance}:Timeout reached, triggering another function and returning.",
        json_payload=json.dumps(
            {
                "file_path": FILE_PATH,
                "time_created": timeCreated,
            }
        ),
    )
    payload = {
        "event": {
                    "name": FILE_PATH,
                    "timeCreated": timeCreated,
                    "instance": instance+1,
                    "backfill": backfill,
                    "search_ids": search_ids,
                    "record_range": record_range

                }
    }

    invoke_cloud_function(settings.BATCH_UPSERT_LEADS_CLOUD_FUNCTION_URL,payload=payload)
    return "Timeout reached, another function instance triggered."

@functions_framework.http
def batch_upsert_leads(request):
    """Responds to any HTTP request.
    Args:
        request: HTTP request object.
    """

    request_json = request.get_json(silent=True)
    if request_json:
        event = request_json.get("event", "No event provided")
    else:
        log_error(
            function_name="batch_upsert_leads",
            endpoint="batch-upsert-leads",
            log_message="No JSON payload received.",
        )
        return {
            "status": "failed",
            "log_message": "No JSON payload received.",
        }
    
    start_time = time.time()  # Track the function execution time
    timeout_limit = 2700  # 45 minutes in seconds
    max_iterations = 100
    iteration_count = 0
    max_instance = 50
    record_upsert_batch_size = 2000
    max_attempts = 1
    base_delay = 10  # seconds
    
    FILE_PATH = event["name"]
    timeCreated = truncate_iso_to_seconds(event["timeCreated"])
    backfill = event.get("backfill",False)
    search_ids =  event.get("search_ids","")
    batch_id = event["batch_id"]
    instance =  event.get("instance",1)
    record_range = event.get('record_range',(1,2000))

    log_context = {
            "filename": event["name"],
            "time_created": truncate_iso_to_seconds(event["timeCreated"]),
            "instance": instance
        }

    # Check the maximum number of instances allowed for processing a single delta file
    if instance > max_instance:
        log_error(
            function_name="batch_upsert_leads",
            endpoint="batch-upsert-leads",
            log_message=f"Instance {instance}:Exceeded the maximum number of Cloud Function instances.",
            error_type=None,
            stack_trace=f"Instance {instance}:Exceeded the maximum number of Cloud Function instances.",
            json_payload=json.dumps(
                {"filenme": FILE_PATH, "time_created": timeCreated}
            ),
        )

        return {
            "status": "failed",
            "log_message": "Exceeded the maximum number of Cloud Function instances.",
            
        }

    # Retry mechanism: try up to max_attempts with exponential backoff on failure
    for attempt in range(1, max_attempts + 1):
        try:
            dynamics_client = get_dynamics_client()

            # Creating the batch_upsert_leads table only in the first instance using project_relevance data and adding core rows.
            if instance == 1:
                # Fetching sales profile data from Dynamics CRM.
                log_default( log_message=f"Instance {instance}:  Fetching sales profile data from Dynamics CRM.", json_payload=json.dumps(log_context ))
                sales_profile_temp_table_id = "sales_profile_temp"

                fetch_sales_rep_info(
                    dynamics_client=dynamics_client,
                    big_query_client=big_query_client,
                    settings=settings,
                    sales_profile_temp_table_id=sales_profile_temp_table_id
                )
                # Executes the CREATE_UNIQUE_COMBINATION_QUERY and load data into batch_upsert_leads table.
                _load_batch_upsert_lead_table(
                    backfill= backfill,
                    search_ids= search_ids,
                    settings= settings,
                    sales_profile_temp= sales_profile_temp_table_id,
                    FILE_PATH= FILE_PATH,
                    big_query_client= big_query_client,
                    batch_id= batch_id
                )
                log_default(log_message=f"Instance {instance}: Pushing consolidated data to fbm_externallead CRM table.")
                external_lead_df = push_consolidated_data(dynamics_client, big_query_client, settings, batch_id, log_context)
                external_lead_dict = dict(zip(external_lead_df['fbm_primaryprojectid'], external_lead_df['fbm_externalleadid']))
            
            # Getting row count of leads
            query = f"SELECT COUNT(*) as row_count FROM {settings.BIGQUERY_DATASET}.batch_upsert_leads"
            result = big_query_client.query_table( query= query)
            leads_count = result[0]['row_count']

            log_default( log_message=f"Instance {instance}:Total row count: {leads_count}.", json_payload=json.dumps( log_context ) )

            log_default(
                   log_message=f"Instance {instance}:Getting project details data.",
                    json_payload=json.dumps( {   **log_context, "record range": record_range}),
                )
            project_details_index = get_project_details(
                settings=settings,
                event= event,
                bq_client=big_query_client
            )
            
            while record_range[0] <= leads_count :
                iteration_count += 1
                # Safeguard to ensure the loop terminates after a reasonable number of iterations.
                if iteration_count > max_iterations:
                    log_error(
                        function_name="batch_upsert_leads",
                        endpoint="batch-upsert-leads",
                        log_message=f"Instance {instance}:Exceeded maximum iterations in while loop.",
                        error_type=None,
                        stack_trace=f"Instance {instance}:Exceeded maximum iterations in while loop.",
                        json_payload=json.dumps(
                            {"filenme": FILE_PATH, "time_created": timeCreated}
                        ),
                    )

                    return {
                        "status": "failed",
                        "log_message": "Exceeded maximum iterations in while loop.",
                        
                    }
                
                # Check execution time of the current cloud function instance; if it exceeds the timeout limit, trigger a new instance.
                if time.time() - start_time > timeout_limit:
                    invoke_another_instance(
                        instance=instance,
                        FILE_PATH=FILE_PATH,
                        timeCreated=timeCreated,
                        backfill=backfill,
                        search_ids=search_ids,
                        record_range=record_range
                    )
                    
                    return {
                        "status": "success",
                        "log_message": f"Timeout reached, another function instance triggered.",
                        "file_path": FILE_PATH,
                        "time_created": timeCreated,
                    }

                log_default(log_message=f"Instance {instance}:Getting project relevance data for file: {FILE_PATH}",
                    json_payload=json.dumps( {   **log_context, "record range": record_range}),
                )
                
                query = f"""SELECT * FROM {settings.BIGQUERY_DATASET}.batch_upsert_leads
                            WHERE row_no between {record_range[0]} and {record_range[1]}"""
                result = big_query_client.query_table( query= query, to_dataframe= True)
                # Replace NaN values with None
                result = result.replace({np.nan: None})
                unique_combinations = result.to_dict(orient="records")

                project_relevance_data_map = {}
                for row in unique_combinations:
                    key = (row["project_id"], row["search_id"])
                    project_relevance_data_map[key] = row

                log_default(
                   log_message=f"Instance {instance}:Getting existing lead data for file: {FILE_PATH}",
                    json_payload=json.dumps( {   **log_context, "record range": record_range}),
                )

                already_exists_leads = get_existing_lead_data( dynamics_client, unique_combinations, settings)
                    
                log_default(
                   log_message=f"Instance {instance}:Separating leads into insert and update lists for file: {FILE_PATH}",
                    json_payload=json.dumps( {   **log_context, "record range": record_range}),
                )
                insert_leads, update_leads = separate_update_insert(
                    already_exists_leads, unique_combinations, project_details_index
                )

                # Fetch confidence threshold from settings
                confidence_threshold = (
                    settings.CONFIDENCE_THRESHOLD if settings.CONFIDENCE_THRESHOLD else None
                )

                update_batch_data = build_batch_update_data(
                    update_leads, project_relevance_data_map, external_lead_dict, confidence_threshold
                )
                insert_batch_data = build_batch_insert_data(
                    insert_leads, project_relevance_data_map, external_lead_dict, confidence_threshold
                )

                log_default(
                    log_message=f"Leads to insert: {len(insert_leads)} , Leads already exist: {len(update_leads)} and Leads to update: {len(update_batch_data)}",
                    json_payload=json.dumps( {   **log_context, "record range": record_range}),
                )


                # loading data in chucks due to limitation of CRM batch api
                if len(insert_batch_data) > 0:
                    # Executing 10 concurrent batch inserts to reduce overall execution time.
                    log_default(
                       log_message=f"Instance {instance}:Batch insert leads started for file: {FILE_PATH}",
                        json_payload=json.dumps( {   **log_context, "record range": record_range}),
                    )
                    process_batches_concurrently(
                        data_to_process= insert_batch_data,
                        method=dynamics_client.send_batch_create,
                        operation_desc= "batch insert leads",
                        entity_name = f"{settings.DM_LEAD_ID}s"
                    )
                    log_default(
                       log_message=f"Instance {instance}:Batch insert leads completed for file: {FILE_PATH}",
                        json_payload=json.dumps( {   **log_context, "record range": record_range}),
                    )

                
                # Updating data in chucks due to limitation of CRM batch api            
                if len(update_batch_data) > 0:
                    # Executing 10 concurrent batch update to reduce overall execution time.
                    log_default(
                        log_message=f"Instance {instance}:Batch update leads started for file: {FILE_PATH}",
                            json_payload=json.dumps( {   **log_context, "record range": record_range}),
                        )
                    
                    process_batches_concurrently(
                        data_to_process= update_batch_data,
                        method=dynamics_client.send_batch_update,
                        operation_desc= "batch update leads",
                        entity_name = f"{settings.DM_LEAD_ID}s",
                        primary_key = "leadid"
                    )                        
                    
                    log_default(
                        log_message=f"Instance {instance}:Batch update leads completed for file: {FILE_PATH}",
                            json_payload=json.dumps( {   **log_context, "record range": record_range}),
                        )
                
                log_default( log_message= f"Instance {instance}:Fetching lead IDs", json_payload=json.dumps( { **log_context, "record range": record_range}))
                # Fetching lead IDs for the leads that were updated or inserted into CRM; these are required for the Sales Category table.
                leadid_ls = get_existing_lead_data( dynamics_client, unique_combinations, settings)
                # Creating a DataFrame of lead IDs to easily join with Sales Category data.
                leadid_df = pd.DataFrame([(k[0], k[1], k[2], v['leadid']) for k, v in leadid_ls.items()], columns=["project_id", "search_id", "owner_id", "leadid"])
                
                # flattening the combinations list to create spearate row for each product category.
                productcategory_data = []
                for row in unique_combinations:
                    if row['materials_valuation'] == "{}":
                        continue
                    materials_valuations = json.loads(row['materials_valuation'])
                    for material in materials_valuations:
                        productcategory_data.append(
                            {
                                "project_id": row['project_id'],
                                "search_id": row['search_id'],
                                "owner_id": row['sales_rep_id'],
                                "fbm_branchid": row['territory_id'],
                                "fbm_productcategoryid": material,
                                "fbm_estimatedrevenue": materials_valuations[material]
                            }   
                        )
                
                productcategory_df = pd.DataFrame(productcategory_data)

                # Joining with the Lead IDs DataFrame.
                productcategory_df = pd.merge(productcategory_df, leadid_df, on=["project_id", "search_id", "owner_id",], how="left")

                productcategory_df = productcategory_df[['leadid','fbm_productcategoryid','fbm_estimatedrevenue','fbm_branchid']]
                productcategory_ls = productcategory_df.to_dict(orient='records')

                # Identifying existing Sales Category entries from the branchopportunity table based on lead_id and primary_product_category_id.
                log_default( log_message= f"Instance {instance}:Identifying existing Sales Category.", json_payload=json.dumps( { **log_context, "record range": record_range}))
                already_exists_branchopportunity = get_existing_branchopportunity(dynamics_client,productcategory_ls,settings)
                
                # Separating opportunities into those that need to be inserted and those that need to be updated.
                log_default( log_message= f"Instance {instance}:Separating opportunities into inserted and updated.", json_payload=json.dumps( { **log_context, "record range": record_range}))

                insert_opportunities, update_opportunities =separate_update_insert_branchopportunity(
                                                                already_exists_branchopportunity,
                                                                branchopportunities=productcategory_ls
                                                            )
                
                insert_opportunity_batch_data = build_batch_opportunities( insert_opportunities)
                update_opportunity_batch_data = build_batch_opportunities( update_opportunities)
               
                log_default(
                    log_message=f"opportunities to insert: {len(insert_opportunities)}  and opportunities to update: {len(update_opportunities)}",
                    json_payload=json.dumps( {   **log_context, "record range": record_range}),
                )
                if len(insert_opportunity_batch_data) > 0:
                    log_default( log_message=f"Instance {instance}:Batch insert opportunities started.", json_payload=json.dumps( {**log_context, "record range": record_range}) )
                    process_batches_concurrently(
                        data_to_process= insert_opportunity_batch_data,
                        method=dynamics_client.send_batch_create,
                        operation_desc= "batch insert opportunities",
                        entity_name = f"{settings.DM_BRANCH_OPPORTUNITY_ID}"
                    )
                    log_default( log_message=f"Instance {instance}:Batch insert opportunities completed for file: {FILE_PATH}", json_payload=json.dumps( {**log_context, "record range": record_range}))

                if len(update_opportunity_batch_data) > 0:
                    # Executing 10 concurrent batch update to reduce overall execution time.
                    log_default(log_message=f"Instance {instance}:Batch update opportunities started for file: {FILE_PATH}", json_payload=json.dumps( {**log_context, "record range": record_range}) )
                    
                    process_batches_concurrently(
                        data_to_process= update_opportunity_batch_data,
                        method=dynamics_client.send_batch_update,
                        operation_desc= "batch update opportunities",
                        entity_name = f"{settings.DM_BRANCH_OPPORTUNITY_ID}",
                        primary_key = "fbm_branchopportunityid"
                    )                        
                    
                    log_default(log_message=f"Instance {instance}:Batch update opportunities completed for file: {FILE_PATH}", json_payload=json.dumps( {   **log_context, "record range": record_range}) )
                
                # Incrementing the record range for batch_upsert_leads
                record_range = range_incrementer(record_range, record_upsert_batch_size)
            return {
                "status": "success",
                "log_message": f"Successfully upserted leads into CRM.",
                "file_path": FILE_PATH,
                "time_created": timeCreated,
            }

        except Exception as e:
            stack_trace = traceback.format_exc()
            if attempt == max_attempts:
                payload = {
                    "event": {
                        "workflow_name": "cloud_function:batch_upsert_leads",
                        "failure_point": "batch_upsert_leads",
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "input_data": event,
                    }
                }
                invoke_cloud_function(
                    settings.WORKFLOW_FAILURE_CLOUD_FUNCTION_URL, payload=payload
                )

                return {
                    "status": "failed",
                    "log_message": str(e),
                    "error_type": type(e).__name__,
                    "stack_trace": stack_trace,
                    "file_path": FILE_PATH,
                    "time_created": timeCreated,
                }
            else:
                log_error(
                    function_name="batch_upsert_leads",
                    endpoint="batch-upsert-leads",
                    log_message=str(e),
                    error_type=type(e).__name__,
                    stack_trace=stack_trace,
                    json_payload=json.dumps(
                        {"filenme": FILE_PATH, "time_created": timeCreated}
                    ),
                )
                log_default(
                   log_message=f"Instance {instance}:Retrying batch_upsert_leads  attempt: {attempt} FILE_PATH: {FILE_PATH}",
                    json_payload=json.dumps(
                        {
                            "file_path": FILE_PATH,
                            "time_created": timeCreated,
                        }
                    ),
                )

            delay = base_delay**attempt
            time.sleep(delay)
