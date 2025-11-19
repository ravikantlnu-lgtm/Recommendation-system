import io
import json
import uuid
from datetime import datetime, timezone
from enum import Enum

from logging_config import log_default
import pandas as pd
from config import get_settings
from google.cloud import secretmanager
from pydantic import BaseModel, confloat
from services import BigQueryManager, DynamicsManager, GeminiClient, GeminiClientConfig
from utils.common import (
    fetch_latest_model_endpoint,
    format_bq_results_as_json,
    truncate_iso_to_seconds,
)
from utils.relevance_prompt_examples import RELEVANCE_PROMPT_EXAMPLES
from utils.prompts import PROJECT_RELEVANCE_PROMPT, RELEVANCE_REASONING_PROMPT

settings = get_settings()


def create_json_file(data_ls):
    json_file = io.StringIO()
    for search_data in data_ls:
        json_file.write(json.dumps(search_data) + "\n")
    json_file.seek(0)  # Reset file pointer to the beginning
    return json_file


def get_search_boolean(query_search_id: str, big_query_client: BigQueryManager):
    """
    select Search name and boolean query from a BigQuery table using the search_id.
    """

    query = f"select id, name, category, boolean from `{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.{settings.SEARCHES_TABLE_ID}` where id = '{query_search_id}'"
    results = big_query_client.query_table(query=query)
    if results is None:
        return None

    return format_bq_results_as_json(results=results)


def get_relevant_materials(big_query_client: BigQueryManager):
    """
    Get a json of relevant materials and divisions they belong to along with the their material_code.
    """
    query = f"select division, material from `{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.{settings.RELEVANT_MATERIALS_TABLE_ID}`"
    results = big_query_client.query_table(query=query)
    if results is None:
        return None

    return format_bq_results_as_json(results=results)


def get_ranking_columns(big_query_client: BigQueryManager):
    """
    Fetch list of ranking columns to use in the LLM from the BigQuery table.
    """

    query = f"select name from `{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.{settings.RANKING_COLUMNS_TABLE_ID}`"
    results = big_query_client.query_table(query=query)
    if results is None:
        return None

    column_names = [row.name for row in results]

    return column_names


def get_territory_name(big_query_client: BigQueryManager, territory_id: str):
    """
    Get the territory name from the BigQuery table using the territory_id.
    """
    query = f"select name from `{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.{settings.TERRITORIES_TABLE_ID}` where id = '{territory_id}' limit 1"

    results = big_query_client.query_table(query=query, to_dataframe=True)

    return results.iloc[0]["name"] if not results.empty else None


def get_relevant_products(big_query_client: BigQueryManager, search_id: str):
    """
    Get list of products sold relevant to the search_id from the BigQuery table.
    """

    query = f"""select fbm_productcatcode 
        from `{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.{settings.SEARCH_PRODUCT_CATEGORY_MAP_TABLE_ID}` 
        where fbm_searchid = '{search_id}'"""

    results = big_query_client.query_table(query=query, to_dataframe=True)

    return results["fbm_productcatcode"].tolist()


def get_project_owner_contacts_cc(
    big_query_client: BigQueryManager, project_id: str, time_created: str
):
    """
    Get the contact information for owner of a project using project_id and time_created.
    """

    query = f"""SELECT
        TO_JSON_STRING(
            STRUCT(
                company.Name AS owner_name,
                (
                    SELECT
                        ARRAY_AGG(p.PhoneNumnber)
                    FROM
                        UNNEST(company.Phones.Phone) AS p
                ) AS phone_numbers
            )
        ) AS owner_json
    FROM
        `{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.{settings.CC_FEED_TABLE_ID}` t,
        UNNEST(t.Companies) AS company_wrap,
        UNNEST(company_wrap.Company) AS company
    WHERE
        t.ProjectID = {project_id} and t.sourceFileCreationTime = '{time_created}'
        AND INSTR(LOWER(company.ROLE), "owner") > 0 
    """

    try:
        results = big_query_client.query_table(query=query, to_dataframe=True)
    except Exception as e:
        print(f"Error executing project owner contacts query: {e}")
        return pd.DataFrame()

    return results


def get_project_owner_contacts_dodge(
    big_query_client: BigQueryManager, project_id: str, time_created: str
):
    """Get the contact information for owner of a project using project_id and time_created."""
    query = f"""
    SELECT
        TO_JSON_STRING(
        STRUCT(
            company_details.CompanyName as owner_name,
            [company_details.CompanyTelephone] as phone_numbers 
        )
        ) as owner_json
    FROM
        `{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.{settings.DODGE_FEED_TABLE_ID}`,
        UNNEST(Companies.Company) AS company_details
    WHERE DRNumber = {project_id} and sourceFileCreationTime = '{time_created}'
    and INSTR(LOWER(company_details.FactorType), "owner") > 0
    """

    try:
        results = big_query_client.query_table(query=query, to_dataframe=True)
    except Exception as e:
        print(f"Error executing project owner contacts query: {e}")
        return pd.DataFrame()

    return results


def get_project_owner_contacts(
    bigquery_client: BigQueryManager, primary_project_id: str
):

    contacts_df = pd.DataFrame({"owner_json": []})

    cc_project_query = f"""SELECT ProjectID, sourceFileCreationTime
    FROM `{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.{settings.CONSOLIDATED_PRIMARY_PROJECT_LEAD_TABLE_ID}`
    WHERE primary_project_id = '{primary_project_id}' and candidate_source = "construct_connect" """

    cc_projects = bigquery_client.query_table(query=cc_project_query, to_dataframe=True)

    for _, row in cc_projects.iterrows():
        project_id = row["ProjectID"]
        time_created = row["sourceFileCreationTime"]
        time_created = time_created.strftime("%Y-%m-%dT%H:%M:%S")

        # Fetch contacts for each project
        contacts = get_project_owner_contacts_cc(
            bigquery_client, project_id, time_created
        )
        contacts_df = pd.concat([contacts_df, contacts], ignore_index=True)

    print(
        "Fetched contacts from ConstructConnect projects: ", contacts_df["owner_json"]
    )

    dodge_project_query = f"""SELECT ProjectID, sourceFileCreationTime
    FROM `{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.{settings.CONSOLIDATED_PRIMARY_PROJECT_LEAD_TABLE_ID}`
    WHERE primary_project_id = '{primary_project_id}' and candidate_source = "dodge" """

    dodge_projects = bigquery_client.query_table(
        query=dodge_project_query, to_dataframe=True
    )

    for _, row in dodge_projects.iterrows():
        project_id = row["ProjectID"]
        time_created = row["sourceFileCreationTime"]
        time_created = time_created.strftime("%Y-%m-%dT%H:%M:%S")

        # Fetch contacts for each project
        contacts = get_project_owner_contacts_dodge(
            bigquery_client, project_id, time_created
        )
        contacts_df = pd.concat([contacts_df, contacts], ignore_index=True)

    print("Fetched contacts from Dodge projects: ", contacts_df["owner_json"])

    return contacts_df


def get_historical_sales_product_location_level(
    big_query_client: BigQueryManager,
    cat_codes: list,
    location: str,
    days: int = 30,
):
    """
    Fetch historical sales data for products sold in the last 'days' days.
    Filter by product list and location.
    """

    # Fetch historical sales based on product list and location
    HISTORICAL_SALES_PRODUCT_QUERY = f"""
    SELECT 
        GROSS_PROFIT_AMT AS gross_profit,
        PRODUCT_PRIMARY_CAT_DESC AS product_category,
        ORDER_LOCATION_DESC AS location,
        ORDER_ID AS order_id,
    FROM `{settings.SALES_PROJECT_ID}.{settings.BIGQUERY_SALES_DATASET}.{settings.GENAI_TABLE}`
    WHERE CREATED_TIMESTAMP >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL {days} DAY)
        and LOWER(PRODUCT_PRIMARY_CAT_CODE) IN UNNEST({cat_codes})
        {f'and INSTR("{location.lower()}", lower(ORDER_LOCATION_DESC)) > 0' if location else ""}
    """

    try:
        results = big_query_client.query_table(
            query=HISTORICAL_SALES_PRODUCT_QUERY, to_dataframe=True
        )
    except Exception as e:
        print(f"Error executing historical sales query: {e}")
        return

    return results if not results.empty else None


def get_historical_data_for_contractor(
    big_query_client: BigQueryManager, contractor_phone_numbers: list, days: int = 30
):
    """
    Fetch historical sales data for a contractor based on their phone numbers.
    """

    HISTORICAL_SALES_CONTRACTOR_QUERY = f"""
    SELECT  
        GROSS_PROFIT_AMT as gross_profit,
        PRODUCT_PRIMARY_CAT_DESC as product_category,
        ORDER_LOCATION_DESC as location,
        ORDER_ID as order_id,
        CUSTOMER_PHONE_NUMBER as customer_phone_number,
        CUSTOMER_EMAIL as customer_email,
        CUSTOMER_CITY as customer_city,
        CUSTOMER_STATE as customer_state,
    FROM `{settings.SALES_PROJECT_ID}.{settings.BIGQUERY_SALES_DATASET}.{settings.GENAI_TABLE}` sales 
        left join `{settings.SALES_PROJECT_ID}.{settings.BIGQUERY_SALES_DATASET}.{settings.SALES_CUSTOMER_TABLE}` customer
        on sales.CUSTOMER_DIM_CODE = CAST(customer.CUSTOMER_WID as string) 
    WHERE sales.CREATED_TIMESTAMP >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL {days} DAY)  
        and CUSTOMER_PHONE_NUMBER IN UNNEST({contractor_phone_numbers})
    """

    try:
        results = big_query_client.query_table(
            query=HISTORICAL_SALES_CONTRACTOR_QUERY, to_dataframe=True
        )
    except Exception as e:
        print(f"Error executing historical sales contractor query: {e}")
        return

    return results if not results.empty else None


def insert_project_relevance(
    query_project_id: str,
    search: str,
    project_territory_id: str,
    time_created: str,
    relevance: str,
    reasoning: list[str],
    confidence: float,
    big_query_client: BigQueryManager,
    distance: float,
    batch_id: str,
    materials_valuation: str,
):

    table_id = settings.PROJECT_RELEVANCE_TABLE_ID
    rows_to_insert = []
    now = datetime.now(timezone.utc)

    # Convert reasoning list to a single string with delimiter
    reasoning_string = " \n ".join(reasoning) if reasoning else ""
    
    rows_to_insert.append(
        {
            "project_id": query_project_id,
            "search_id": search,
            "territory_id": project_territory_id,
            "time_created": time_created,
            "relevance": relevance,
            "reasoning": reasoning_string,
            "confidence": confidence,
            "source": "construct_connect",
            "distance": distance,
            "materials_valuation": materials_valuation,
            "batch_id": batch_id,
            "modified_on": now.strftime("%Y-%m-%d %H:%M:%S.%f UTC"),
        }
    )

    try:
        big_query_client.insert_rows(table_id, rows_to_insert)

    except Exception as e:
        raise Exception(f"Failed to insert rows into BigQuery: {e}")
    return rows_to_insert


class ProjectRelevanceBoolean(Enum):
    VERY_HIGH = "very high"
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    VERY_LOW = "very low"
    NOT_RELEVANT = "not relevant"


class ProjectClassification(BaseModel):
    Relevance: ProjectRelevanceBoolean
    Reasoning: str


class ProjectClassificationWithConfidence(BaseModel):
    Relevance: ProjectRelevanceBoolean
    Reasoning: list[str]  # List of reasoning strings
    Confidence: confloat(ge=0.0, le=1.0)  # Confidence score between 0.0 and 1.0


def get_secret(project_number: str, secret_name: str):
    client = secretmanager.SecretManagerServiceClient()
    secret_version_name = (
        f"projects/{project_number}/secrets/{secret_name}/versions/latest"
    )
    response = client.access_secret_version(request={"name": secret_version_name})

    return response.payload.data.decode("utf-8")


def llm_prompt_project_relevance(
    project_data: dict,
    search: str,
    search_terms: str,
    total_valuation: float,
    sales_data_product_location: str = None,
    sales_data_contractor_level: str = None,
    historical_days: int = 30,
    relevance_examples: dict = RELEVANCE_PROMPT_EXAMPLES,
):
    prompt = PROJECT_RELEVANCE_PROMPT.format(
        project_data=project_data,
        search=search,
        search_terms=search_terms,
        total_valuation=(
            total_valuation if total_valuation != 0.0 else "Not provided"
        ),
        historical_days=historical_days,
        sales_data_product_location="* Relevant Products: * "
        + sales_data_product_location,
        sales_data_contractor_level="* Sales with this Contractor: * "
        + sales_data_contractor_level,
    )

    if relevance_examples:
        print("Fetching examples with same search name...")
        examples_prompt = ""

        # Get list of examples based on search name
        search_examples = None

        # Iterate through the keys of the examples dictionary
        for key, examples_list in relevance_examples.items():
            # Check if the current key is a substring of the search
            if key.lower() in search.lower():
                search_examples = examples_list
                break  # Stop after finding the first match

        if search_examples:
            print(f"Found {len(search_examples)} examples for search: {search}")

            # Iterate through the examples and format them to prompt
            for idx, example in enumerate(search_examples):

                # Fetch the example data
                project_data_example = example.get("Project Data", None)
                search_example = example.get("Search", None)
                boolean_filter_example = example.get("Boolean Filter", None)
                output_example = example.get("Output", None)

                # Add example to prompt if all fields are present and valid
                if (
                    isinstance(project_data_example, dict)
                    and isinstance(search_example, str)
                    and isinstance(boolean_filter_example, str)
                    and isinstance(output_example, dict)
                ):

                    examples_prompt += f""" 
                    
                    **Example {idx + 1}:**

                        **Input Data:**

                            **Project Data:**
                            {json.dumps(project_data_example, indent=4)}

                            **Search**
                            {search}

                            **Boolean Filter**
                            {boolean_filter_example}

                        **Output:**
                            {json.dumps(output_example, indent=4)}
                    """
        else:
            print(f"No examples found for search: {search}")

        if examples_prompt:
            prompt += examples_prompt

    model, is_tuned_model = fetch_latest_model_endpoint(
        llm_prompt_type="assign_relevance"
    )

    if is_tuned_model:
        model_type = "tuned"
    else:
        model_type = "base"

    config = GeminiClientConfig(
        project_id=settings.PROJECT_ID,
        location=settings.TUNED_MODEL_REGION,
        model=model, 
        model_type=model_type
    )

    gemini_client = GeminiClient(config=config)

    return gemini_client.generate_structured(prompt, ProjectClassification)


def llm_generate_relevance_reasoning(
    project_data: dict,
    search: str,
    search_terms: str,
    relevance_classification: str,  # Added input for the pre-determined relevance
    total_valuation: float,
    sales_data_product_location: str, 
    sales_data_contractor_level: str,
    historical_days: int = 30,  # Optional parameter for historical sales days
):

    """
    Generates reasoning for a given project relevance classification using an LLM.
    """
    
    prompt = RELEVANCE_REASONING_PROMPT.format(
        project_data_json=json.dumps(project_data),
        search=search,
        search_terms=search_terms,
        total_valuation=(
            total_valuation if total_valuation != 0.0 else "Not provided"
        ),
        historical_days=historical_days,
        sales_data_product_location="* Relevant Products: * "
        + sales_data_product_location,
        sales_data_contractor_level="* Sales with this Contractor: * "
        + sales_data_contractor_level,
        relevance_classification=relevance_classification,
    )

    # Consider if a different llm_prompt_type string is needed if using a specific endpoint/model for reasoning
    model, is_tuned_model = fetch_latest_model_endpoint(
        llm_prompt_type="assign_relevance_reasoning"
    )  # Or perhaps "generate_relevance_reasoning"?

    if is_tuned_model:
        model_type = "tuned"
    else:
        model_type = "base"

    config = GeminiClientConfig(
        model=model, 
        model_type=model_type,
        project_id=settings.PROJECT_ID,
        location=settings.REGION,
    )
    
    gemini_client = GeminiClient(config=config)

    # The LLM should return JSON matching ProjectClassificationWithConfidence including the provided relevance and its generated reasoning
    return gemini_client.generate_structured(
        prompt, ProjectClassificationWithConfidence
    )


def get_uuid():
    return str(uuid.uuid4())

def remove_irrelevant_materials(project_data: dict, search_materials_df: pd.DataFrame, query_search_id: str):
    """
    Remove irrelevant materials from the project data.
    """

    # Filter out materials based on search id
    relevant_materials = search_materials_df[search_materials_df['fbm_searchid'] == query_search_id]

    # Fetch material codes from the relevant materials
    relevant_material_codes = relevant_materials['code'].tolist()
    relevant_material_codes = [str(code) for code in relevant_material_codes if pd.notna(code)]

    # Make a copy of the project data to avoid modifying the original data
    project_data_relevant_materials = project_data.copy()

    # Iterate through the project data to remove irrelevant materials
    for column_name, value in project_data_relevant_materials.items():
        try: 
            if column_name == "Materials_Material": 
                project_data_relevant_materials[column_name] = [] # Set the column to an empty list
                continue 
            # Check if the column has material codes 
            if "RSMeansMaterialDivisions" in column_name: 
                # Remove materials if they are not in the relevant material codes
                filtered_materials = [
                    material for material in value 
                    if (isinstance(material, dict) and 'Code' in material and str(material['Code']) in relevant_material_codes)
                ]
                # Update the project data with the filtered materials
                project_data_relevant_materials[column_name] = filtered_materials

        except Exception as e:
            log_default(
                log_message=f"Error removing materials for project: {e}",
                json_payload=json.dumps({
                    "project_data": project_data_relevant_materials,
                    "search": query_search_id
                }),
            )
            continue

    return project_data_relevant_materials