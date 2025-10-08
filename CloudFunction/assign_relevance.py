import io
import json
import logging
import os
import re
import time
import traceback
import pandas as pd

import functions_framework
from config import get_settings
from logging_config import log_default, log_error
from services import BigQueryManager, DynamicsManager
from utils.assign_relevance_utils import (
    get_historical_data_for_contractor,
    get_historical_sales_product_location_level,
    get_project_owner_contacts,
    get_relevant_products,
    get_search_boolean,
    get_territory_name,
    insert_project_relevance,
    llm_generate_relevance_reasoning,
    llm_prompt_project_relevance,
    remove_irrelevant_materials
)
from utils.common import get_secret, fetch_project_data, get_ranking_columns

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


@functions_framework.http
def assign_relevance(request):
    """Responds to any HTTP request.
    Args:
        request: HTTP request object.
    """
    query_project_id = None
    search_id = None
    max_retries = 3
    backoff = 5

    for attempt in range(max_retries):
        try:
            request_json = request.get_json()
            if request_json is None:
                raise ValueError("Invalid request data")

            if request_json["match"]:
                query_project_id = request_json["project_id"]
                search_id = request_json["search_id"]
                territory_id = request_json["territory_id"]
                time_created = request_json["time_created"]
                distance_from_territory = request_json["distance_from_territory"]
                territory_idx = request_json["territory_idx"]
                search_materials_json = request_json["search_materials_json"]
                materials_valuation = request_json["materials_valuation"]
                batch_id = request_json["batch_id"]

                log_default(
                    log_message="Project Classification request received",
                    json_payload=json.dumps(request_json),
                )

                search_materials_df = pd.read_json(search_materials_json)

                response_json = process_project_assignment(
                    query_project_id=query_project_id,
                    query_search_id=search_id,
                    project_territory_id=territory_id,
                    time_created=time_created,
                    distance_from_territory=distance_from_territory,
                    territory_idx=territory_idx,
                    search_materials_df=search_materials_df,
                    materials_valuation=materials_valuation,
                    batch_id= batch_id
                )

                # Check if the response contains an error type
                if isinstance(response_json, dict) and response_json.get("error_type"):
                    error_type = response_json["error_type"]
                    error_message = response_json.get("log_message", "Unknown error")
                    
                    log_default(
                        log_message=f"process_project_assignment returned error: {error_type} - {error_message} (Attempt {attempt + 1}/{max_retries})",
                        json_payload=json.dumps(request_json),
                    )
                    
                    # Retry for certain error types, but not for data not found errors
                    if error_type == "PROJECT_NOT_FOUND" or error_type == "SEARCH_NOT_FOUND" or error_type == "TERRITORY_NOT_FOUND":
                        # Don't retry for data not found errors
                        return {
                            "status": "failed",
                            "log_message": error_message,
                            "error_type": error_type,
                            "project_id": query_project_id,
                            "search_id": search_id,
                            "territory_id": territory_id,
                        }

                    # Retry for LLM errors 
                    else: 
                        if attempt < max_retries - 1:
                            time.sleep(backoff * (2**attempt))
                            continue
                        # If last attempt, return error
                        else:
                            return {
                                "status": "failed",
                                "log_message": "process_project_assignment returned error after all retries",
                                "error_type": error_type,
                                "project_id": query_project_id,
                                "search_id": search_id,
                                "territory_id": territory_id,
                            }

                # If no error, return success
                return {
                    "status": "success",
                    "log_message": "assign_relevance function completed",
                    **response_json,
                    **request_json,
                }

            # If match is False, return success
            else:
                return {
                    "status": "success",
                    "log_message": "Skipping the assign_relevance function because the match condition is False.",
                    **request_json,
                }

        except Exception as e:
            stack_trace = traceback.format_exc()
            log_error(
                function_name="classify_project_cloud_function",
                endpoint="classify_project",
                log_message=str(e),
                error_type=type(e).__name__,
                stack_trace=stack_trace,
                json_payload=json.dumps(
                    {"project_id": query_project_id, "search_id": search_id}
                ),
            )
            return {
                "status": "failed",
                "log_message": str(e),
                "error_type": type(e).__name__,
                "stack_trace": stack_trace,
                "project_id": query_project_id,
                "search_id": search_id,
                "territory_id": territory_id,
            }


def process_project_assignment(
    query_project_id: str,
    query_search_id: str,
    project_territory_id: str,
    time_created: str,
    distance_from_territory: float,
    territory_idx: int,
    search_materials_df: pd.DataFrame,
    batch_id:str,
    materials_valuation: str, 
):
    """
    Process the project search classification.
    Args:
        query_project_id (str): The project ID.
    Returns:
        dict: The JSON response received from the LLM prompt.
    """


    ranking_cols = get_ranking_columns(big_query_client)
    if ranking_cols is None:
        ranking_cols = []
    select_columns = ", ".join([f"`{col}`" for col in ranking_cols])

    # Fetch merged project data from ConstructConnect and Dodge
    project_data = fetch_project_data(big_query_client, query_project_id, select_columns)

    if project_data is None:
        log_default(
            log_message="Project not found",
            json_payload=json.dumps(
                {
                    "project_id": query_project_id,
                    "search_id": query_search_id,
                    "territory_id": project_territory_id,
                    "time_created": time_created,
                }
            ),
        )
        # Return PROJECT_NOT_FOUND error
        return { 
            "error": "PROJECT_NOT_FOUND",
            "log_message": "Project not found",
            "project_id": query_project_id,
            "search_id": query_search_id,
            "territory_id": project_territory_id,
        }

    project_data = json.loads(project_data)
    project_data = project_data[0]
    project_data["closest_branch"] = distance_from_territory

    log_default(
        log_message="Project data retrieved", json_payload=json.dumps(project_data)
    )

    # Get boolean search query from search_id
    boolean_search_result = get_search_boolean(query_search_id, big_query_client)
    if not boolean_search_result:
        log_default(
            log_message="Search not found",
            json_payload=json.dumps(
                {
                    "project_id": query_project_id,
                    "search_id": query_search_id,
                    "territory_id": project_territory_id,
                    "time_created": time_created,
                }
            ),
        )
        # Return SEARCH_NOT_FOUND error
        return { 
            "error": "SEARCH_NOT_FOUND",
            "log_message": "Search not found",
            "project_id": query_project_id,
            "search_id": query_search_id,
            "territory_id": project_territory_id,
        }

    boolean_search_json = json.loads(boolean_search_result)
    log_default(
        log_message="Boolean search details retrieved",
        json_payload=json.dumps(
            {
                "project_id": query_project_id,
                "search_id": query_search_id,
                "territory_id": project_territory_id,
                "time_created": time_created,
                **boolean_search_json[0],
            }
        ),
    )

    territory_name = None
    if project_territory_id:
        # Get territory name from BigQuery
        territory_name = get_territory_name(
            big_query_client=big_query_client, territory_id=project_territory_id
        )
        if not territory_name:
            print("Territory not found")
            log_default(
                log_message="Territory not found",
                json_payload=json.dumps(
                    {
                        "project_id": query_project_id,
                        "search_id": query_search_id,
                        "territory_id": project_territory_id,
                        "time_created": time_created,
                    }
                ),
            )
            # Return TERRITORY_NOT_FOUND error
            return { 
                "error": "TERRITORY_NOT_FOUND",
                "log_message": "Territory not found",
                "project_id": query_project_id,
                "search_id": query_search_id,
                "territory_id": project_territory_id,
            }

    # Get relevant products using search ID
    relevant_product_cat_codes = get_relevant_products(big_query_client, query_search_id)
    if not relevant_product_cat_codes:
        print("No relevant products found")
        log_default(
            log_message="No relevant products found",
            json_payload=json.dumps(
                {
                    "project_id": query_project_id,
                    "search_id": query_search_id,
                    "territory_id": project_territory_id,
                    "time_created": time_created,
                }
            ),
        )
        relevant_cat_codes = []
    else:
        relevant_cat_codes = [str(cat_code) for cat_code in relevant_product_cat_codes]

    materials_valuation_dict = json.loads(materials_valuation)

    # Calculate total valuation for all categories and materials under this search
    total_valuation = 0.0 
    for material in materials_valuation_dict:
        total_valuation += materials_valuation_dict[material]


    # -------------------------------------------- #
    # Fetch historical sales data to use in LLM prompt
    # -------------------------------------------- #

    # Initialize profit summary variables
    profit_summary_product_location_stats_json = "Not provided"
    profit_summary_contractor_stats_json = "Not provided"

    # ------- Sales data for this search and location ------- #

    # Get historical sales data for relevant products and this branch location
    sales_data_product_location_level = get_historical_sales_product_location_level(
        big_query_client=big_query_client,
        cat_codes=relevant_cat_codes,
        location=territory_name,
        days=settings.HISTORICAL_SALES_DAYS,
    )

    if sales_data_product_location_level is None:
        print("No historical sales data found for the relevant products and location")
        log_default(
            log_message="No historical sales data found",
            json_payload=json.dumps(
                {
                    "project_id": query_project_id,
                    "search_id": query_search_id,
                    "territory_id": project_territory_id,
                    "time_created": time_created,
                }
            ),
        )
    else:
        # Generate summary statistics of profit for each product
        # The data is already a pandas DataFrame from the query
        df = sales_data_product_location_level  # type: ignore
        
        df["product_category"] = df["product_category"].apply(
            lambda x: x.lower()
        )
        
        # Create a more readable summary for each product category
        product_summary_dict = {}
        for category in df["product_category"].unique():
            category_data = df[df["product_category"] == category]
            
            # Calculate units sold (count of orders) and average gross profit
            units_sold = len(category_data)
            avg_gross_profit = category_data["gross_profit"].mean()
            
            product_summary_dict[category] = {
                "units_sold": int(units_sold),
                "avg_gross_profit": float(round(avg_gross_profit, 2))
            }
        
        # Convert to a readable string format
        profit_summary_product_location_stats_json = json.dumps(product_summary_dict)
        print("Product location sales summary:", profit_summary_product_location_stats_json)

    # ------- Sales data for this contractor ------- #

    # Initialize variables for phone numbers and data for contractor
    phone_numbers = None
    sales_data_contractor_level = None

    # Get project owner contact information
    project_owner_contact_information = get_project_owner_contacts(
        bigquery_client=big_query_client,
        primary_project_id=query_project_id,
    )

    if project_owner_contact_information is None:
        log_default(
            log_message="No project owner contact information found",
            json_payload=json.dumps(
                {
                    "project_id": query_project_id,
                    "search_id": query_search_id,
                    "territory_id": project_territory_id,
                    "time_created": time_created,
                }
            ),
        )
    else:
        # Extract phone numbers from project owner information
        owner_json_rows = project_owner_contact_information["owner_json"].tolist()
        phone_numbers = []
        for entry in owner_json_rows:
            try:
                owner_dict = json.loads(entry)
                if "phone_numbers" in owner_dict and owner_dict["phone_numbers"] is not None:
                    phone_numbers.extend(owner_dict["phone_numbers"])
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON: {e} for entry: {entry}")
                continue

        phone_numbers = [
            re.sub(r"[^0-9]", "", s) for s in phone_numbers
        ]  # Normalize phone numbers by removing non-numeric characters
        phone_numbers = list(set(phone_numbers))  # Remove duplicates
        print("Extracted phone numbers:", phone_numbers)

    # Fetch historical data for sales with this contractor
    if phone_numbers and len(phone_numbers) > 0:
        sales_data_contractor_level = get_historical_data_for_contractor(
            big_query_client=big_query_client,
            contractor_phone_numbers=phone_numbers,
            days=settings.HISTORICAL_SALES_DAYS,
        )

    if sales_data_contractor_level is None:
        print("No historical sales data found for the contractor")
        log_default(
            log_message="No historical sales data found for the contractor",
            json_payload=json.dumps(
                {
                    "project_id": query_project_id,
                    "search_id": query_search_id,
                    "territory_id": project_territory_id,
                    "time_created": time_created,
                }
            ),
        )
    else:
        # Generate summary statistics of profit for this contractor
        profit_summary_contractor_stats = { 
            "sales_made": int(sales_data_contractor_level[['gross_profit']].count()[0]),
            "avg_gross_profit": float(sales_data_contractor_level[['gross_profit']].mean()[0].round(2)),
        }
        print(profit_summary_contractor_stats)

        # Convert the DataFrame to JSON to pass to LLM
        profit_summary_contractor_stats_json = json.dumps(profit_summary_contractor_stats)

    if territory_idx and territory_idx >= 0:
        time.sleep(territory_idx * 5)

    # LLM prompt to get project relevance
    output = llm_prompt_project_relevance(
        project_data=project_data,
        search=boolean_search_json[0]["name"],
        search_terms=boolean_search_json[0]["boolean"],
        total_valuation=total_valuation,
        sales_data_product_location=profit_summary_product_location_stats_json,
        sales_data_contractor_level=profit_summary_contractor_stats_json,
    )

    if output is None:
        print("LLM response is None")
        log_default(
            log_message="LLM response is None",
            json_payload=json.dumps(
                {
                    "project_id": query_project_id,
                    "search_id": query_search_id,
                    "territory_id": project_territory_id,
                    "time_created": time_created,
                }
            ),
        )
        return { 
            "error": "LLM_ERROR",
            "log_message": "LLM response is None",
            "project_id": query_project_id,
            "search_id": query_search_id,
            "territory_id": project_territory_id,
        }

    output = output.model_dump_json()
    print("LLM prompt output:", output)

    # Get reasoning
    try:

        project_data_relevant_materials = remove_irrelevant_materials(project_data, search_materials_df, query_search_id)

        reasoning = llm_generate_relevance_reasoning(
            project_data=project_data_relevant_materials,
            search=boolean_search_json[0]["name"],
            search_terms=boolean_search_json[0]["boolean"],
            relevance_classification=json.loads(output)["Relevance"],
            total_valuation=total_valuation,
            sales_data_product_location=profit_summary_product_location_stats_json,
            sales_data_contractor_level=profit_summary_contractor_stats_json,
        )

    except Exception as e:
        print(f"Error occurred: {str(e)}")
        stack_trace = traceback.format_exc()
        log_error(
            function_name="classify_project_cloud_function",
            endpoint="classify_project",
            log_message=str(e),
            error_type=type(e).__name__,
            stack_trace=stack_trace,
            json_payload=json.dumps(
                {
                    "project_id": query_project_id,
                    "search_id": query_search_id,
                    "territory_id": project_territory_id,
                }
            ),
        )
        return { 
            "error": "LLM_ERROR",
            "log_message": "Error generating LLM reasoning",
            "project_id": query_project_id,
            "search_id": query_search_id,
            "territory_id": project_territory_id,
        }

    if reasoning is None:
        print("LLM reasoning is None")
        log_default(
            log_message="LLM reasoning is None",
            json_payload=json.dumps(
                {
                    "project_id": query_project_id,
                    "search_id": query_search_id,
                    "territory_id": project_territory_id,
                    "time_created": time_created,
                }
            ),
        )
        return { 
            "error": "LLM_ERROR",
            "log_message": "LLM reasoning returned None response",
            "project_id": query_project_id,
            "search_id": query_search_id,
            "territory_id": project_territory_id,
        }

    reasoning = reasoning.model_dump_json()
    print("LLM reasoning output:", reasoning)

    log_default(
        log_message="LLM prompt output received",
        json_payload=json.dumps(
            {
                "project_id": query_project_id,
                "search_id": query_search_id,
                "territory_id": project_territory_id,
                "time_created": time_created,
                **json.loads(output),
                **json.loads(reasoning),
            }
        ),
    )

    json_output = json.loads(output)
    reasoning = json.loads(reasoning)
    json_output["Reasoning"] = reasoning["Reasoning"]
    json_output["Confidence"] = reasoning["Confidence"]

    log_default(
        log_message="LLM output parsed into JSON",
        json_payload=json.dumps(
            {
                "project_id": query_project_id,
                "search_id": query_search_id,
                "territory_id": project_territory_id,
                "time_created": time_created,
                **json_output,
            }
        ),
    )

    row = insert_project_relevance(
        query_project_id=query_project_id,
        search=boolean_search_json[0]["id"],
        project_territory_id=project_territory_id,
        time_created=time_created,
        relevance=json_output["Relevance"],
        reasoning=json_output["Reasoning"],
        confidence=json_output["Confidence"],
        big_query_client=big_query_client,
        distance=distance_from_territory,
        materials_valuation=materials_valuation, # dictionary of product category and material valuation
        batch_id= batch_id    
    )

    log_default(
        log_message="Project relevance inserted into BigQuery",
        json_payload=json.dumps(
            {
                **row[0],
            }
        ),
    )

    return json_output
