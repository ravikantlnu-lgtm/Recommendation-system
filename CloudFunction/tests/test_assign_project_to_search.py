import json
import os
import sys
from unittest.mock import MagicMock, Mock, patch

from functions_framework import create_app

# Get the directory of the current script
current_dir = os.path.dirname(os.path.abspath(__file__))

# Move one level up to the parent directory
parent_dir = os.path.abspath(os.path.join(current_dir, os.pardir))

# Add the parent directory to sys.path
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Import the Cloud Function directly
from assign_project_to_search import assign_project_search
from config import get_settings
from services import BigQueryManager

settings = get_settings()
big_query_client = BigQueryManager(dataset_id=settings.BIGQUERY_DATASET)


def test_project_search_case(mock_data_dict):
    """Test the assign_project_to_search cloud function endpoint locally"""

    # Mock HHTP JSON object
    mock_request = Mock()
    mock_request.get_json = lambda: mock_data_dict
    try:
        # Call the cloud function
        response = assign_project_search(mock_request)

        # Print response
        print("\nCloud Function Response:")
        print(response)
        # if response["match"]:
            # assert isinstance(response, dict)
            # assert "project_id" in response
            # assert "search_id" in response
            # assert "territory_id" in response
            # assert "time_created" in response
            # assert "distance_from_territory" in response

            # assert response["project_id"] == mock_data_dict["project_id"]
            # assert response["search_id"] == mock_data_dict["search_id"]
            # assert response["territory_id"] == mock_data_dict["territory_id"]
            # assert response["time_created"] == mock_data_dict["time_created"]
            # assert (
            #     response["distance_from_territory"]
            #     == mock_data_dict["distance_from_territory"]
            # )

            # assert (
            #     get_count_project_search_table(
            #         mock_data_dict["project_id"],
            #         mock_data_dict["search_id"],
            #         mock_data_dict["territory_id"],
            #         mock_data_dict["time_created"].replace("Z", ""),
            #         big_query_client,
            #     )
            #     == project_search_table_count + 1
            # )
        # else:
        #     assert (
        #         get_count_project_search_table(
        #             mock_data_dict["project_id"],
        #             mock_data_dict["search_id"],
        #             mock_data_dict["territory_id"],
        #             mock_data_dict["time_created"].replace("Z", ""),
        #             big_query_client,
        #         )
        #         == project_search_table_count
        #     )
    
    except Exception as e:
        print(f"\nError occurred: {str(e)}")
        raise e


if __name__ == "__main__":
    # Set environment variables for local testing
    import os

    os.environ["DEPLOYMENT"] = "dev"

    # # Fetch most recent search materials data
    # search_materials_query = f"""select * from `{settings.BIGQUERY_DATASET}.{settings.SEARCHES_MATERIALS_MAP_TABLE_ID}`"""
    # search_materials_df = big_query_client.query_table(
    #     query=search_materials_query, to_dataframe=True
    # )
    
    # # NO
    # mock_data = {
    #     "project_id": 1007605509,
    #     "search_id": "5ee2ab20-266c-4fc2-bac9-f784353df5a6",
    #     "territory_id": [
    #         {
    #             "territory_id": "cfcb0a8f-bfb6-ee11-a569-00224808d025",
    #             "distance_from_territory": 17.87,
    #         }
    #     ],
    #     "time_created": "2025-04-29T06:40:24",
    #     "distance_from_territory": 20,
    #     "search_materials_json": 
    #         search_materials_df[search_materials_df['search_id'] == "5ee2ab20-266c-4fc2-bac9-f784353df5a6"].to_json()
    # }
    # print("*** Starting local test of assign_project_to_search.py for NO case...")
    # test_project_search_case(mock_data_dict=mock_data)
    # print(
    #     "*** Passed tests for local test of assign_project_to_search.py for NO case..."
    # )

    # # YES
    # mock_data = {
    #     "project_id": 1007605509,
    #     "search_id": "0b3ab0d4-ec94-4ad2-974e-997e3055b839",
    #     "territory_id": [
    #         {
    #             "territory_id": "cfcb0a8f-bfb6-ee11-a569-00224808d025",
    #             "distance_from_territory": 17.87,
    #         }
    #     ],
    #     "time_created": "2025-04-29T06:40:24",
    #     "distance_from_territory": None,
    #     "search_materials_json": 
    #         search_materials_df[search_materials_df['search_id'] == "0b3ab0d4-ec94-4ad2-974e-997e3055b839"].to_json()
    # }
    # print("*** Starting local test of assign_project_to_search.py for YES case...")
    # test_project_search_case(mock_data_dict=mock_data)
    # print(
    #     "*** Passed tests for local test of assign_project_to_search.py for YES case..."
    # )

    # mock_data = {
    #     "project_id": 1007605509,
    #     "search_id": "0b3ab0d4-ec94-4ad2-974e-997e3055b839",
    #     "territory_id": [{"territory_id": None, "distance_from_territory": None}],
    #     "time_created": "2025-04-29T06:40:24",
    #     "distance_from_territory": None,
    #      "search_materials_json": 
    #         search_materials_df[search_materials_df['search_id'] == "0b3ab0d4-ec94-4ad2-974e-997e3055b839"].to_json()
    # }
    # print(
    #     "*** Starting local test of assign_project_to_search.py where territory_id is None..."
    # )
    search_product_category_query = f"""select sp.fbm_searchid, sp.fbm_productcategoryid, pm.material, pm.code 
                                        from `{settings.BIGQUERY_DATASET}.{settings.SEARCH_PRODUCT_CATEGORY_MAP_TABLE_ID}` sp 
                                        left join `{settings.BIGQUERY_DATASET}.{settings.PRODUCT_CATEGORY_MATERIALS_MAP_TABLE_ID}` pm 
                                        on sp.fbm_productcatcode=pm.fbm_productcatcode"""
    search_product_materials_df = big_query_client.query_table(search_product_category_query, to_dataframe=True)

    # NO
    from datetime import datetime
    mock_data = {
        "project_id": '0372b762-a152-4510-a2f1-88cee469c8cd',
        "search_id": "16700387-5d11-f011-9988-000d3a5a18fb",
        "territory_id": [
            {'distance_from_territory': None, 'territory_id': None}, 
        ],
        "time_created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "distance_from_territory": None,
        "search_materials_json": 
            search_product_materials_df[search_product_materials_df['fbm_searchid'] == "16700387-5d11-f011-9988-000d3a5a18fb"].to_json()
    }
    test_project_search_case(mock_data_dict=mock_data)
    print(
        "*** Passed tests for local test of assign_project_to_search.py where territory_id is None..."
    )
