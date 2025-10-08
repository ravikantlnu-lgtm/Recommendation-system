import json
import os
import sys
from unittest.mock import MagicMock, Mock, patch

from functions_framework import create_app
from google.cloud import secretmanager

# Get the directory of the current script
current_dir = os.path.dirname(os.path.abspath(__file__))

# Move one level up to the parent directory
parent_dir = os.path.abspath(os.path.join(current_dir, os.pardir))

# Add the parent directory to sys.path
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Import the Cloud Function directly
from assign_relevance import assign_relevance
from config import get_settings
from services import BigQueryManager

settings = get_settings()
big_query_client = BigQueryManager(dataset_id=settings.BIGQUERY_DATASET)


def get_count_project_relevance_table(
    test_project_id,
    test_search_id,
    test_territory_id,
    test_time_created,
    big_query_client,
):
    query = f"select count(*) from `{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.{settings.PROJECT_RELEVANCE_TABLE_ID}` where project_id = {test_project_id} and search_id = '{test_search_id}' and territory_id = '{test_territory_id}' and time_created = '{test_time_created}'"
    results = big_query_client.query_table(query=query)

    if results is None:
        return None
    return results[0][0]


def get_secret(secret_id, version_id="latest"):
    """Get secret from GCP Secret Manager"""
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{settings.PROJECT_ID}/secrets/{secret_id}/versions/{version_id}"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")


def test_assign_relevance(mock_data_dict):
    """Test the classify_project_cloud_function endpoint locally"""

    # Mock HTTP request object
    mock_request = Mock()
    mock_request.get_json = lambda: mock_data_dict

    if not mock_data_dict["match"]:
        response = assign_relevance(mock_request)
        print("\nCloud Function Response:")
        print(json.dumps(response, indent=2))
        assert (
            response["log_message"]
            == "Skipping the assign_relevance function because the match condition is False."
        )
        return

    # Call the cloud function
    response = assign_relevance(mock_request)

    # Print response
    print("\nCloud Function Response:")
    print(json.dumps(response, indent=2))

    assert isinstance(response, dict)
    assert "Relevance" in response
    assert "Reasoning" in response
    assert "Confidence" in response
    # except Exception as e:
    #     print(f"\nError occurred: {str(e)}")
    #     raise e


if __name__ == "__main__":
    # Set environment variables for local testing
    import os

    os.environ["DEPLOYMENT"] = "dev"
    try:
        # Pull dynamics credentials from Secret Manager
        dynamics_cred = get_secret("dynamics_cred")  # Replace with your secret name
        os.environ["dynamics_cred"] = dynamics_cred
    except Exception as e:
        print(f"Error fetching secrets: {e}")
        # Fallback to empty credentials for local testing
        os.environ[
            "dynamics_cred"
        ] = """{
            "TENANT_ID" : "",
            "APPLICATION_ID" : "",
            "CLIENT_SECRET" : ""
        }"""

    print("Starting local test of assign_relevance.py...")

    search_product_category_query = f"""select sp.fbm_searchid, sp.fbm_productcategoryid, pm.material, pm.code 
                                        from `{settings.BIGQUERY_DATASET}.{settings.SEARCH_PRODUCT_CATEGORY_MAP_TABLE_ID}` sp 
                                        left join `{settings.BIGQUERY_DATASET}.{settings.PRODUCT_CATEGORY_MATERIALS_MAP_TABLE_ID}` pm 
                                        on sp.fbm_productcatcode=pm.fbm_productcatcode"""
    search_product_materials_df = big_query_client.query_table(search_product_category_query, to_dataframe=True)

    mock_data = {
        "match": True,
        "project_id": "0372b762-a152-4510-a2f1-88cee469c8cd",
        "search_id": "16700387-5d11-f011-9988-000d3a5a18fb",
        "territory_id": None,
        "time_created": "2025-07-10T14:47:10",
        "distance_from_territory": None,
        "territory_idx": 0,
        "search_materials_json": search_product_materials_df[search_product_materials_df["fbm_searchid"] == "16700387-5d11-f011-9988-000d3a5a18fb"].to_json(orient="records"),
        "materials_valuation": """{"ea7ce57d-82da-ee11-904d-00224808d025": 103111.14, "8cc0e478-82da-ee11-904d-00224808df0d": 69368.1}"""
    } 

    
    # Convert Python dictionary to JSON string
    json_data = json.dumps(mock_data)

    # Deserialize JSON string back to Python dictionary
    parsed_data = json.loads(json_data)
    print("parsed_data", parsed_data)

    test_assign_relevance(parsed_data)

    # print("Starting local test of assign_relevance.py when 'no match' is passed...")
    # mock_data = {"match": False}
    # test_assign_relevance(mock_data)
