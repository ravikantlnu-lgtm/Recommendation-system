import numpy as np
import pandas as pd 
import json
from enum import Enum 
from pydantic import BaseModel
from typing import Type, TypeVar, Optional, Literal, NamedTuple
from config import get_settings 
from fuzzywuzzy import fuzz 

from services import GeminiClient, GeminiClientConfig
from utils.common import fetch_latest_model_endpoint, get_secret

settings = get_settings()

class Match(Enum): 
    MATCH = "match"
    NO_MATCH = "no_match"
    UNSURE = "unsure"

class ProjectDuplicateResult(BaseModel): 
    project_match: Match 
    Reasoning: str

class DeduplicationResult(NamedTuple):
    project_1_id: int
    project_2_id: int
    distance: float
    match: str
    reasoning: str



T = TypeVar('T')

# Define the source column names for ConstructConnect and Dodge Data
# These mappings are used to extract relevant columns from the project data for deduplication
source_column_names = { 
    "construct_connect": {
        'id_col': 'ProjectID',
        'title_col': 'Title',
        'lat_col': 'Latitude',
        'long_col': 'Longitude',
        'desc_cols': ['Details_Detail_Scope', 'Details_Detail_Notes', 'Details_Detail_Details', 
                    'Parameters_Parameter_Ownership', 'Parameteres_Parameter_WorkType', 
                    'ParentCategories_ParentCategory', 'ParentCategories_PrimaryCategoryName', 'Valuation_Value']
    }, 
    "dodge": {
        'id_col': 'DRNumber',
        'title_col': 'ProjectTitle',
        'lat_col': 'Lat',
        'long_col': 'Long',
        'desc_cols': ['StatusText', 'FeaturesInfo', 'OwnershipType', 
                    'TypeOfWork', 'MarketSegment', 'PrimaryProjectType', 'Valuation']
    }
}

def fetch_owner_from_cc(project_data: pd.Series) -> Optional[str]:
    """ 
    This function extracts the owner a project from ConstructConnect.
    
    "Companies" field is expected to be a list. 
    The first item in this list expected to be a dictionary containing "Company" list. 
    Searches for a company with the role of "owner" and returns its name if found.
    """

    companies_data = project_data.get("Companies")
    if not isinstance(companies_data, (list, np.ndarray)) or not companies_data:
        return None 
    
    company_group = companies_data[0] 
    if not isinstance(company_group, dict):
        return None
    
    company_list = company_group.get("Company") 
    if not isinstance(company_list, (list, np.ndarray)):
        return None
    
    # Iterate through the list of companies to find the owner
    for company_details in company_list: 
        if isinstance(company_details, dict): 
            role = company_details.get("Role") 
            if isinstance(role, str) and role.lower() == "owner":
                company_name = company_details.get("Name")
                if isinstance(company_name, str):
                    return company_name.lower().strip() # Normalize the name to lowercase and strip whitespace
            
    return None

def fetch_owner_from_dodge(project_data: pd.Series) -> Optional[str]:
    """ 
    This function extracts the owner a project from Dodge Data. 

    The "Companies" field is expected to be a dictionary. 
    The "Company" field within this dictionary is expected to be a list of companies. 
    Searches for a company with the "FactorType" of "owner" and returns its name if found.
    """

    companies_data = project_data.get("Companies") 
    if not isinstance(companies_data, dict):
        return None 
    
    companies_list = companies_data.get("Company") 
    if not isinstance(companies_list, (list, np.ndarray)):
        return None
    
    # Iterate through the list of companies to find the owner
    for company_details in companies_list:
        if isinstance(company_details, dict): 
            factor_type = company_details.get("FactorType") 
            if isinstance(factor_type, str) and factor_type.lower() == "owner":
                company_name = company_details.get("CompanyName")
                if isinstance(company_name, str):
                    return company_name.lower().strip() # Normalize the name to lowercase and strip whitespace

    return None

def fetch_owner_from_project_data(project_data: pd.Series, source: Literal["construct_connect", "dodge"]) -> Optional[str]:
    """ 
    This function fetches the owner of a project from its data based on the source type. 
    """
    
    try: 
        if source == "construct_connect": 
            return fetch_owner_from_cc(project_data) # Fetch owner from ConstructConnect data
        elif source == "dodge": 
            return fetch_owner_from_dodge(project_data) # Fetch owner from Dodge data
        
    except Exception as e:
        print(f"Error fetching owner from project data: {e}")
        return None
    
def llm_generate_duplication_result(project_1_json: str, 
                                    project_2_json: str, 
                                    project_1_title: str, 
                                    project_2_title: str,
                                    distance: float, 
                                    project_1_owner: str = None, 
                                    project_2_owner: str = None):
    
    """ 
    This function determines if two projects are duplicates and generates match results and reasining using an LLM. 
    Args:
        - project_1_json (str): JSON data for Project 1.
        - project_2_json (str): JSON data for Project 2.
        - project_1_title (str): Title of Project 1.
        - project_2_title (str): Title of Project 2.
        - distance (float): Distance between the two projects in miles.
        - project_1_owner (str, optional): Owner of Project 1. Defaults to None.
        - project_2_owner (str, optional): Owner of Project 2. Defaults to None.
    """

    prompt = f"""

        Your task is to determine if two construction projects are duplicates of each other based on the provided details.

        **Instructions:**
        1. **Carefully analyze the provided JSON data** details for Project 1 and Project 2, including features, plans, and description of work.

        2. **Analyze the project titles** to understand the context and scope of each project.

        3. **Consider the distance** between the two projects, which is provided in miles. 

        4. **Consider the project owners** if that information is available.

        5. **Determine if the two projects are duplicates** or unsure based on the provided information. Use the overall context of the projects, including their titles, descriptions, and distance apart.
       
            * Information that would be relevant to the decision: 
                - Project titles 
                - Project descriptions 
                - Location 
            * Information that would not be relevant to the decision:
                - Project IDs 
                - Dates of actions, updates, or bids 
                - Bid dates or amounts

        6. **Formulate reasoning** for your decision. 
        
        7. **Respond as a "match", "no match", or "unsure"** based on your analysis, along with your reasoning.

        **Project 1:** 

        **Title:** {project_1_title} 

        {"**Owner:** " + project_1_owner if project_1_owner else ""}

        **JSON Data:**
        {project_1_json}

        **Project 2:**

        **Title:** {project_2_title}

        {"**Owner:** " + project_2_owner if project_2_owner else ""}

        **JSON Data:**

        {project_2_json}

        **Distance:** {distance} miles
        
        **Example Output Format:** 
        {{
            "project_match": "match" | "no_match" | "unsure",
            "Reasoning": "Your reasoning here."
        }}

        """
    
    gemini_api_key = get_secret(
        project_number=settings.PROJECT_NUMBER,
        secret_name=settings.GEMINI_API_KEY_SECRET_NAME,
    )

    # Consider if a different llm_prompt_type string is needed if using a specific endpoint/model for reasoning
    model, is_tuned_model = fetch_latest_model_endpoint(
        llm_prompt_type="base_llm"
    )  

    if is_tuned_model:
        model_type = "tuned"
    else:
        model_type = "base"

    # Initialize client and configuration 
    config = GeminiClientConfig(
        model=model, 
        model_type=model_type,
        project_id=settings.PROJECT_ID,
        location=settings.REGION
    )
    gemini_client = GeminiClient(config=config)

    # Generate structured response 
    return gemini_client.generate_structured(prompt, ProjectDuplicateResult)

def is_same_project(project_1_data: dict,
                    project_2_data: dict,
                    project_1_column_mappings: dict,
                    project_2_column_mappings: dict,
                    distance: float,
                    p1_owner: str = None, 
                    p2_owner: str = None,
                    distance_threshold_miles: float = 0.05,
                    fuzzy_threshold: float = 50) -> (float, ProjectDuplicateResult):
    
    """
    Criteria for match: 
        - Project locations are within a certain distance threshold (default 0.5 miles)
        - Project titles are similar enough (default fuzzy threshold 50)
        - If both criteria are met, use LLM to confirm match, no match, or unsure. 
            - Passes project descriptive data, distance, title, and owner. 

    Args:
        - project_1_data (pd.Series): Data for Project 1.
        - project_2_data (pd.Series): Data for Project 2.
        - project_1_column_mappings (dict): Column mappings for Project 1.
        - project_2_column_mappings (dict): Column mappings for Project 2.
        - p1_owner (str, optional): Owner of Project 1. Defaults to None.
        - p2_owner (str, optional): Owner of Project 2. Defaults to None.
        - distance_threshold_miles (float, optional): Distance threshold in miles for considering projects as duplicates. Defaults to 0.5.
        - fuzzy_threshold (float, optional): Fuzzy matching threshold for project titles. Defaults to 50.
    Returns: 
        - distance (float): Distance between the two projects in miles.
        - ProjectDuplicateResult: The match status and reasoning.
    """ 

    try: 
        # Fetch project titles 
        p1_title = project_1_data[project_1_column_mappings['title_col']]
        p2_title = project_2_data[project_2_column_mappings['title_col']] 

        # Fetch project coordinates
        p1_coords = (
            float(project_1_data[project_1_column_mappings['lat_col']]),
            float(project_1_data[project_1_column_mappings['long_col']])
        )

        p2_coords = (
            float(project_2_data[project_2_column_mappings['lat_col']]),
            float(project_2_data[project_2_column_mappings['long_col']])
        )

    except KeyError as e:
        print(f"KeyError: {e}. Please check the column names in the data.")
        return 
    except ValueError as e:
        print(f"ValueError: {e}. Please check the data types of the coordinates.")
        return
    except Exception as e:
        print(f"Unexpected error: {e}. Please check the input data.")
        return 

    # Calculate distance between projects
    # try: 
    #     distance = haversine_distance_miles_numpy(
    #         p1_coords[0],
    #         p1_coords[1],
    #         np.array([p2_coords[0]]), 
    #         np.array([p2_coords[1]]),
    #     )[0]
    # except Exception as e:
    #     print(f"Error calculating distance: {e}")
    #     return
    
    # If distance exceeds threshold, return no match
    # if distance > distance_threshold_miles:
    #     return distance, ProjectDuplicateResult(
    #         project_match=Match.NO_MATCH, 
    #         Reasoning= f"""Distance (miles) between projects exceeds threshold: 
    #                     distance {distance} > threshold {distance_threshold_miles}"""
    #     )
    
    # Normalize titles
    # p1_title = str(p1_title).lower().strip()
    # p2_title = str(p2_title).lower().strip()

    # # Check if titles are similar enough
    # match_ratio = fuzz.partial_ratio(p1_title, p2_title) # use most similar substring 

    # If titles are not similar enough, return no match
    # if match_ratio < fuzzy_threshold:
    #     return distance, ProjectDuplicateResult(
    #         project_match=Match.NO_MATCH, 
    #         Reasoning=f"""Titles '{p1_title}' and '{p2_title}' are not similar enough: 
    #                     match ratio {match_ratio} < threshold {fuzzy_threshold}"""
    #     )
    
    # Convert project data to JSON string for LLM processing 
    # Keep only the description columns as specified in the mappings to avoid uncessary data passed to LLM 
    project_1_desc_cols = project_1_column_mappings['desc_cols']
    project_2_desc_cols = project_2_column_mappings['desc_cols']

    project_1_desc_dict  = {k: project_1_data[k] for k in project_1_desc_cols if k in project_1_data}

    # project_1_desc_dict = project_1_data[[col for col in project_1_desc_cols if col in project_1_data]]
    project_1_desc_json = json.dumps(project_1_desc_dict)
    project_2_desc_dict  = {k: project_2_data[k] for k in project_2_desc_cols if k in project_2_data}

    # project_2_desc_dict = project_2_data[[col for col in project_2_desc_cols if col in project_2_data]]
    project_2_desc_json = json.dumps(project_2_desc_dict)

    # Generate LLM response to determine if projects are duplicates
    llm_match_response = llm_generate_duplication_result(
        project_1_json=project_1_desc_json, 
        project_2_json=project_2_desc_json,
        project_1_title=p1_title, 
        project_2_title=p2_title, 
        distance=distance,
        project_1_owner=p1_owner,
        project_2_owner=p2_owner
    )

    return distance, llm_match_response

def process_one_project_pair_deduplication(project_1_data: dict,
                                           project_2_data: dict,
                                           project_1_source: Literal["construct_connect", "dodge"],
                                           project_2_source: Literal["construct_connect", "dodge"],
                                           distance: float) -> DeduplicationResult:
    
    """
    This function processes a pair of projects to determine if they are duplicates. 
    It is designed to be flexible in data sources and column mappings, allowing for deduplication from different sources like ConstructConnect and Dodge.
    Note: This function takes project data as pd.Series, which is expected to be a single row of project data.

    Args:
        - project_1_data (pd.Series): Data for Project 1.
        - project_2_data (pd.Series): Data for Project 2.
        - project_1_source: Source of Project 1 data. Must be one of "construct_connect" or "dodge".
        - project_2_source: Source of Project 2 data. Must be one of "construct_connect" or "dodge".
        - distance: distance between the projects.
    Returns:
        - DeduplicationResult: A named tuple containing the project IDs, distance, match status, and reasoning.
    """ 

    # Fetch project IDs from data 
    p1_id = project_1_data[source_column_names[project_1_source]['id_col']]
    p2_id = project_2_data[source_column_names[project_2_source]['id_col']]

    p1_owners = project_1_data['owner_names']
    p2_owners = project_2_data['owner_names']

    p1_unique_owners = ', '.join(owner for owner in set(p1_owners)) if p1_owners else None
    p2_unique_owners = ', '.join(owner for owner in set(p2_owners)) if p2_owners else None
    
    # Fetch owners from project data based on source
    # p1_owner = fetch_owner_from_project_data(
    #     project_data=project_1_data, 
    #     source=project_1_source
    # )

    # p2_owner = fetch_owner_from_project_data(
    #     project_data=project_2_data, 
    #     source=project_2_source
    # )

    # Run the deduplication logic to determine if projects are duplicates
    distance_between_projects, match_response = is_same_project(
        project_1_data=project_1_data,
        project_2_data=project_2_data,
        project_1_column_mappings=source_column_names[project_1_source],
        project_2_column_mappings=source_column_names[project_2_source],
        distance=distance,
        p1_owner=p1_unique_owners,
        p2_owner=p2_unique_owners,
    )

    # Extract match status and reasoning from the response
    match = match_response.project_match.value 
    reasoning = match_response.Reasoning

    return DeduplicationResult(p1_id, p2_id, distance_between_projects, match, reasoning)
