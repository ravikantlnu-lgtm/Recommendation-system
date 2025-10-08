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
    prompt = f"""

     **Objective:** Classify ConstructConnect projects as very high, high, moderate, low, very low, or not relevant.

        **Instructions:**

        1. **Analyze the provided JSON data:** Understand the project details, including relevant fields and data points. The JSON data representing ConstructConnect project is provided in **Project Data**.

        2. **Utilize Search Terms:** Identify relevant products, materials, and phrases. The search terms are provided in the **Search Terms** section.

        3. **Consider Project Types:** Identify project type. Determine if the project is specialized and has high opportunity for work and visibility. 
        Examples of specialized projects are: 
            * Hospital and health services
            * Churches
            * Commercial real estate
            * Large residential apartments/dormitories
            * University/College buildings
            * Auditoriums
            * Senior living homes
        Examples of non-specialized projects with very low priority are:
            * One-time projects
            * Small residential projects
            * Golf courses

        4. **Note the Materials Value for the Search:** Identify the valuation relevant materials, which is provided.

        5. **Analyze the Historical Sales Data:** If historical sales data is provided, analyze the statistics to understand past performance. 
            Historical data can be provided at the product level or contractor level or both.
            * If historical sales data is provided at the product level, the data includes all products related to the search query that have been sold. 
            * If historical sales data is provided at the contractor level, the data includes previous sales made with this project's contractor. 

        6. **Identify Building Type**: Identify building type, including interior complexity and specialized work. 
        
        7. **Identify Building Size**: Identify the size of the project, including number of stories, height of building, and number of total buildings in the project.

        8. **Identify Locations and Distance:** Identify the project location and distance from nearest branch. Consider if a branch is too far away from a location. 
        Urban areas should have closer branches, while rural areas can have branches further away.

        9. **Identify Associated Brands:** Identify associated brands to the product. Associated brands include: 
            * Armstrong Ceilings 
            * Sto 
            * Dryvit

        10. **Identify Available Plans:** Identify if the project has detailed and available plans and specs.

        11. **Classify Projects:**
            a. Prioritize projects based on how relevant the inputs are to the search terms.
            b. Next, prioritize projects based on the project type, as specified in the previous steps. Deprioritize non-specialized projects. 
            c. Next, prioritize projects which has a high valuation of relevant materials, as specified in the previous steps. Deprioritize projects with low valuation of materials.
            d. Next, prioritize projects based on historical sales data, as specified in the previous steps. Deprioritize projects with poor historical sales for the products or with the contractor.
            e. Next, prioritize building types based on how complex the interior work is, as specified in the previous steps. Deprioritize projects with little interior work. 
            f. Next, prioritize projects based on the size of the building, as specified in the previous steps. Deprioritize projects with small buildings or few stories.
            g. Next, prioritize projects that have reasonable distance to the nearest branch, as specified in the previous steps. Deprioritize projects that are too far away from a branch.
            h. Next, prioritize projects that have associated brands, as specified in the previous steps. Lack of associated brands will not lower the priority.
            i. Next, increase priority if the project has detailed plans and specs. Lack of plans and specs will not lower the priority. 
            j. When other factors are equal, prioritize higher-value projects (e.g., higher total dollar amount).

        12. **Estimate Relevancy:** Estimate the relevancy of each project based on the above factors and total dollar amount.

        **Input Data:**
            **Project Data:**
            {project_data}

            **Search**
            {search}

            **Boolean Filter**
            {search_terms}

            **Materials Valuation**
            {total_valuation if total_valuation != 0.0 else "Not provided"}

            **Historical Sales Data for the last {historical_days} days:** 
            
            {"* Relevant Products: * " + sales_data_product_location}
            
            {"* Sales with this Contractor: * " + sales_data_contractor_level}

        **Example Output:**
        {{
            "Relevance": classification,
            "Reasoning": "Reasoning for classification."
        }}
       
        """

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
    
    # Updated prompt focusing on generating reasoning for a given classification
    prompt = f"""

      **Objective:** Generate the reasoning for a **given** ConstructConnect project relevance classification and a confidence score.

      **Instructions:**

      1.  **Analyze the provided JSON data:** Understand the project details, including relevant fields and data points. The JSON data representing the ConstructConnect project is provided in **Project Data**.

      2.  **Utilize Search Terms:** Identify mentions of relevant products, materials, and phrases within the project data. The search terms are provided in the **Search Terms** section and potentially refined in the **Search** section.

      3.  **Consider Project Types:** Identify the project type. Note if it's a specialized type with high opportunity (e.g., Hospital, University, Commercial Real Estate, Large Residential) or a lower priority type (e.g., small residential, one-time jobs).

      4.  **Identify Materials Valuation:** Identify the valuation of relevant materials provided. This is provided in the **Materials Valuation** section.

      5. **Analyze the Historical Sales Data:** If historical sales data is provided, analyze the statistics to understand past performance. 
        Historical data can be provided at the product level or contractor level or both. 
        * If historical sales data is provided at the product level, the data includes all products related to the search query that have been sold. 
        * If historical sales data is provided at the contractor level, the data includes previous sales made with this project's contractor. 

      6.  **Identify Building Type**: Identify the building type and infer the potential interior complexity and need for specialized work based on it.

      7.  **Identify Building Size**: Identify the size of the project, including number of stories, height of building, and number of total buildings in the project.

      8.  **Identify Locations and Distance:** Note the project location and its distance from the nearest branch (if provided or inferable). Consider the implications of distance (urban vs. rural context).

      8.  **Identify Associated Brands:** Check for mentions of specific associated brands like Armstrong Ceilings, Sto, Dryvit.

      9.  **Identify Available Plans:** Note if detailed plans and specifications are mentioned as being available.

      10.  **Generate Reasons:** Based on your analysis of the factors above (Steps 1-9) and the **provided Relevance Classification**, formulate a list of reasons. 
            These must explain *why* the project aligns with the given classification by connecting specific project details to justify the relevance level.
            Include all relevant factors from the previous steps in your reasoning. Be concise, brief, and to the point. Prioritize the most relevant factors.
            Here is an example of a reasoning list: 
            * Owned by Federal government
            * Medical Facility
            * FRP relevant material cost: $20,000
            * Plans and specs are available
             
      11. **Confidence Score**: Provide a confidence score between 0.0 (Low Confidence) and 1.0 (High Confidence) reflecting your certainty in the assigned **Relevance Score** and your Reasoning.
        * **Base this confidence primarily on the clarity, completeness, and consistency of the input information** used to generate reasoning in steps 1-8.
        * **Calibration Guide:**
            * **> 0.9:** Reserve for cases where **ALL critical factors** are evaluated using **explicit, complete, and unambiguous** input data.
            * **0.7 - 0.9:** Use when most factors (including critical ones) are clear, but perhaps some **secondary information** is inferred/missing, or there's **very minor ambiguity**.
            * **0.3 - 0.6:** Use when **one or more critical factors** rely partially on **inference, contain some ambiguity, or have missing details**, OR if multiple secondary factors are uncertain.
            * **< 0.3:** Use when there is **significant missing information, ambiguity, or contradiction** affecting **one or more critical factors**, making the calculated Relevance and reasoning highly speculative or uncertain.

      12. **Response Logic:** Do not include information directly from the project description. Do not include details about the search terms or matching the search term in your response. The reasoning should be limited to the most relevant aspects of the project that contribute to the relevance. The bullet points should prioritize information that is not included in the project description.

      **Example Output Format:**
      {{
          "Relevance": "Provided Relevance Classification",
          "Reasoning": [
              "Reason 1",
              "Reason 2",
              "Reason 3",
              "Reason 4"
          ],
          "Confidence": Confidence Score
      }}

      **Input Data:**
          **Project Data:**
          {json.dumps(project_data)} # Ensure JSON is properly formatted string

          **Search:**
          {search}

          **Boolean Filter / Search Terms:**
          {search_terms}

          **Materials Valuation:**
          {total_valuation if total_valuation != 0.0 else "Not provided"}

          **Historical Sales Data for the last {historical_days} days:** 
        
            {"* Relevant Products: * " + sales_data_product_location}
            
            {"* Sales with this Contractor: * " + sales_data_contractor_level}

          **Provided Relevance Classification:**
          {relevance_classification}
      """

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