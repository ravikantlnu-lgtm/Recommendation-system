import json
from datetime import datetime, timezone
from enum import Enum
import pandas as pd

from config import get_settings
from logging_config import log_default
from pydantic import BaseModel
from services import BigQueryManager, GeminiClient, GeminiClientConfig
from utils.common import fetch_latest_model_endpoint, get_secret
from utils.prompts import ASSIGN_PROJECT_SEARCH_PROMPT

settings = get_settings()

project_id = settings.PROJECT_ID
dataset_id = settings.BIGQUERY_DATASET


def insert_assigned_search(
    query_project_id: str,
    query_search_id: str,
    project_territory_id: str,
    time_created: str,
    is_related: str,
    big_query_client: BigQueryManager,
    materials_valuation: str, 
):
    """
    Insert the project-search pair in the assigned_search table.
    """
    table_id = settings.ASSIGNED_SEARCH_TABLE_ID
    rows_to_insert = []

    rows_to_insert.append(
        {
            "project_id": query_project_id,
            "search_id": query_search_id,
            "territory_id": f"{project_territory_id}",
            "time_created": datetime.fromisoformat(
                time_created.replace("Z", "+00:00")
            ).strftime("%Y-%m-%d %H:%M:%S"),
            "is_related": is_related,
            "materials_valuation": materials_valuation,
        }
    )
    big_query_client.insert_rows(table_id, rows_to_insert)

    log_default(
        log_message=f"New {len(rows_to_insert)} row/rows have been added to the {table_id} table.",
        json_payload=json.dumps(rows_to_insert),
    )


def get_territory_id(query_search_id: str, big_query_client: BigQueryManager):
    """
    Selects all rows and columns from a BigQuery table.
    """
    query = f"select territory_id from `{project_id}.{dataset_id}.{settings.SEARCH_TERRITORY_TABLE_ID}` where search_id = '{query_search_id}'"

    results = big_query_client.query_table(query=query)

    return results


class ProjectSearchAssignment(Enum):
    YES = "YES"
    NO = "NO"


class ProjectSearchAssignmentResult(BaseModel):
    Project_related_to_Search: ProjectSearchAssignment
    Reasoning: str


def run_prompt_assign_project_search(
    search_name: str, search_query: str, cc_project_json: str
):
    """
    Classifies a ConstructConnect project's relevance to a Search using boolean filters and structured output.

    Args:
        search_name (str): name of the search being evaluated.
        search_query (str): The boolean filters to apply.
        cc_project_json (str): The JSON data representing the ConstructConnect project.

    Returns:
        str: The JSON response containing the project relevance classification.
    """

    prompt = ASSIGN_PROJECT_SEARCH_PROMPT.format(
        cc_project_json=cc_project_json,
        search_name=search_name,
        search_query=search_query,
    )

    model, is_tuned_model = fetch_latest_model_endpoint(
        llm_prompt_type="assign_project_search"
    )

    if is_tuned_model:
        model_type = "tuned"
    else:
        model_type = "base"

    config = GeminiClientConfig(
        model=model, 
        model_type=model_type,
        project_id=settings.PROJECT_ID,
        location=settings.REGION
    )
    gemini_client = GeminiClient(config=config)

    return gemini_client.generate_structured(prompt, ProjectSearchAssignmentResult)

def calculate_materials_valuation(project_data: dict, search_id: str, search_product_materials_df: pd.DataFrame) -> dict:
    
    # Filter out materials based on search name
    relevant_materials = search_product_materials_df[search_product_materials_df['fbm_searchid'] == search_id]
    
    # Fetch material codes from the relevant materials
    relevant_material_codes = relevant_materials['code'].tolist()
    relevant_material_codes = [str(code) for code in relevant_material_codes if pd.notna(code)]

    material_to_product_category_map = {} # Maps material code to product category
    valuation_dict = {} # Maps product category to valuation

    # Fetch which product categories relate to which materials 
    for _, row in relevant_materials.iterrows():
        material_to_product_category_map[str(row['code'])] = row['fbm_productcategoryid']
        valuation_dict[row['fbm_productcategoryid']] = 0.0 # Initialize valuation for each product category to 0 

    # Iterate through the project data to calculate valuation
    for column_name, value in project_data.items():
        try: 
            # Check if the column has material cost informations 
            if "RSMeansMaterialDivisions" in column_name: 
                # Iterate through all materials 
                for materials_information in value:
                    # Check if material information contains the code  
                    if isinstance(materials_information, dict) and 'Code' in materials_information:
                        code = str(materials_information['Code'])
                        # If the code is in the relevant materials, add its valuation to the correct product category 
                        if code in relevant_material_codes and 'TotalCostValue' in materials_information: 
                            print("Code found: ", code)
                            # Find which product category the material belongs to  
                            related_product_category = material_to_product_category_map[code]
                            print("related product category: ", related_product_category)
                            # Add the valuation to the correct product category valuation 
                            valuation_dict[related_product_category] += float(materials_information['TotalCostValue']) 
        
        except Exception as e:
            log_default(
                log_message=f"Error calculating material valuation for project: {e}",
                json_payload=json.dumps({
                    "project_data": project_data,
                    "search_id": search_id 
                }),
            )
            continue

    return valuation_dict