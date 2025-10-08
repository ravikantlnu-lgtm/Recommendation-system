import json
from datetime import datetime, timezone
import uuid
from dateutil import parser
import numpy as np 
import math

from config import get_settings
from google import genai
from google.cloud import aiplatform, secretmanager
from services import BigQueryManager
from vertexai.generative_models import GenerativeModel
from google.auth.transport.requests import Request
import requests
from google.oauth2 import service_account
from requests.exceptions import ReadTimeout, RequestException

settings = get_settings()


def format_bq_results_as_json(results: list):
    """
    Formats BigQuery results into a JSON array of dictionaries.

    Args:
        results: An iterable of BigQuery Row objects.

    Returns:
        A JSON string representing the results, or None if results is empty.
    """
    if not results:
        return None

    result_list = []
    for row in results:
        row_dict = dict(row.items())
        result_list.append(row_dict)

    return json.dumps(result_list, indent=4, default=str)


def get_ranking_columns(big_query_client: BigQueryManager):

    query = f"select name from `{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.{settings.RANKING_COLUMNS_TABLE_ID}`"
    results = big_query_client.query_table(query=query)
    
    if results is None:
        return None

    column_names = [row.name for row in results]

    return column_names


def get_cc_row_data(
    query_project_id: str,
    time_created: str,
    select_columns: list,
    big_query_client: BigQueryManager,
):
    """
    selects all rows and columns from a BigQuery table.

    Args:
        project_id (str): The ID of the Google Cloud project.
        dataset_id (str): The ID of the BigQuery dataset.
        table_id (str): The ID of the BigQuery table.

    Returns:
        list: A list of rows, where each row is a google.cloud.bigquery.table.Row.
              Returns None if an error occurs.
    """
    query = f"select {select_columns} from `{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.{settings.CC_FEED_TABLE_ID}` where ProjectID = {query_project_id} and sourceFileCreationTime = '{time_created}'"
    results = big_query_client.query_table(query=query)

    if results is None:
        return None

    return format_bq_results_as_json(results=results)


def get_search_boolean(query_search_id: str, big_query_client: BigQueryManager):
    """
    select Search name and boolean query from a BigQuery table using the search_id.
    """

    query = f"select id, name, category, boolean from `{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.{settings.SEARCHES_TABLE_ID}` where id = '{query_search_id}'"
    results = big_query_client.query_table(query=query)
    if results is None:
        return None

    return format_bq_results_as_json(results=results)

def get_secret(project_number: str, secret_name: str):
    client = secretmanager.SecretManagerServiceClient()
    secret_version_name = (
        f"projects/{project_number}/secrets/{secret_name}/versions/latest"
    )
    response = client.access_secret_version(request={"name": secret_version_name})

    return response.payload.data.decode("utf-8")


def fetch_latest_model_endpoint(llm_prompt_type: str) -> bool: 

    aiplatform.init(project=settings.PROJECT_ID, location=settings.REGION)
    if llm_prompt_type == 'assign_project_search': 
        endpoint_id = settings.LATEST_TUNED_LLM_ENDPOINT_PROJECT_TO_SEARCH
    elif llm_prompt_type == 'assign_relevance': 
        endpoint_id = settings.LATEST_TUNED_LLM_ENDPOINT_ASSIGN_RELEVANCE
    elif llm_prompt_type == 'assign_relevance_reasoning':
        endpoint_id = settings.LLM_ENDPOINT_REASONING
    elif llm_prompt_type == 'base_llm':
        endpoint_id = settings.BASE_LLM_MODEL
    else: 
        endpoint_id = None
    
    if endpoint_id and endpoint_id.startswith("projects/"): 
    # Try to fetch the model using the endpoint ID
        try:
            model = GenerativeModel(endpoint_id)
            print(f"Model {model} retrieved successfully.")
            return endpoint_id, True 
        except Exception as e: 
            print(f"Error retrieving model: {e}")
    elif endpoint_id:
        return endpoint_id, False
            
    else:
        return "gemini-2.0-flash", False

def get_uuid():
    return str(uuid.uuid4())


def invoke_cloud_function(CLOUD_FUNCTION_URL, payload=None, wait_to_complete = False):
    """
    Invokes a Google Cloud Function with the provided URL and payload in a fire-and-forget manner.
    This function uses a service account to authenticate and send a POST request to the specified
    Cloud Function URL. It is designed for scenarios where the response from the Cloud Function
    is not required, and the request is sent with a short timeout.
    Args:
        CLOUD_FUNCTION_URL (str): The URL of the Cloud Function to invoke.
        payload (dict, optional): The JSON payload to send in the POST request. Defaults to None.
    Raises:
        RuntimeError: If there is an exception other than a read timeout while sending the request.
    Notes:
        - The function retrieves service account credentials from a secret named "default-service-account".
        - The credentials are used to generate an identity token for authenticating the request.
        - A read timeout is expected in fire-and-forget mode and is handled silently.
        - Any other request exceptions are raised as a RuntimeError.
    """
    # Load service account credentials
    service_account_info = json.loads(get_secret(project_number=settings.PROJECT_ID, 
                                                 secret_name="default-service-account"))
    credentials = service_account.IDTokenCredentials.from_service_account_info(
        service_account_info,
        target_audience=CLOUD_FUNCTION_URL
    )
    # Refresh the credentials to get the identity token
    credentials.refresh(Request())
    token = credentials.token
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    try:
        if wait_to_complete:
            timeout = None  # Waiting for the Cloud Function execution to complete
        else:
            timeout = 5 # Just enough to send the request
            
        # Fire-and-forget: short timeout and no response handling
        response = requests.post(
            CLOUD_FUNCTION_URL,
            headers=headers,
            json=payload,
            timeout= timeout  
        )
    except ReadTimeout:
        # Read timeout is expected in fire-and-forget mode
        pass
    except RequestException as e:
        # Raise all other exceptions
        raise RuntimeError(f"Cloud Function trigger failed: {e}")

def truncate_iso_to_seconds(timestamp_str: str) -> str:
    """
    Truncates an ISO 8601 timestamp string to seconds precision.
    
    Example: "2025-02-06T01:30:47.465Z" to "2025-02-06T01:30:47"
    """
    dt = parser.isoparse(timestamp_str)
    return dt.strftime("%Y-%m-%dT%H:%M:%S")

def haversine_distance_miles_numpy(lat1, lon1, lat2_array, lon2_array):
    """
    Calculates the haversine distance between a single point (lat1, lon1)
    and an array of points (lat2_array, lon2_array) using NumPy for efficiency.

    Args:
        lat1 (float): Latitude of the single point.
        lon1 (float): Longitude of the single point.
        lat2_array (numpy.ndarray): Array of latitudes for the other points.
        lon2_array (numpy.ndarray): Array of longitudes for the other points.

    Returns:
        numpy.ndarray: Array of distances in miles.
    """
    R_miles = 6371.0 * 0.621371  # Earth's radius in miles

    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = np.radians(lat2_array)
    lon2_rad = np.radians(lon2_array)

    delta_lat = lat2_rad - lat1_rad
    delta_lon = lon2_rad - lon1_rad

    a = (
        np.sin(delta_lat / 2) ** 2
        + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(delta_lon / 2) ** 2
    )
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))

    distances = R_miles * c
    return distances

def fetch_project_data(big_query_client: BigQueryManager, query_project_id: str, select_columns: str):
    query = f"""
        SELECT {select_columns} FROM `{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.{settings.COALESCED_PRIMARY_PROJECT_TABLE_ID}`
        WHERE `ProjectID` = '{query_project_id}'
        order by insert_timestamp desc 
        limit 1
    """
    results = big_query_client.query_table(query=query) 

    if results is None:
        return None

    return format_bq_results_as_json(results=results)

