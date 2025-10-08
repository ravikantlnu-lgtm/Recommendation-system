import os 
import sys 
import pandas as pd

# Get the directory of the current script
current_dir = os.path.dirname(os.path.abspath(__file__))

# Move one level up to the parent directory
parent_dir = os.path.abspath(os.path.join(current_dir, os.pardir))
utils_dir = os.path.join(parent_dir, "utils")

# Add the parent directory to sys.path
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
if utils_dir not in sys.path:
    sys.path.insert(0, utils_dir)
    
from deduplicate_projects_utils import process_one_project_pair_deduplication
from config import get_settings
from services import BigQueryManager

settings = get_settings()
big_query_client = BigQueryManager(dataset_id=settings.BIGQUERY_DATASET)

# Helper function to fetch project data from BigQuery based on project ID and source type
def fetch_project_from_bigquery(project_id, big_query_client, source_type):
    if source_type == "construct_connect": 
        query = f"""SELECT *, 
            `Addresses_Address`[SAFE_OFFSET(0)].Longitude AS Longitude,
            `Addresses_Address`[SAFE_OFFSET(0)].Latitude AS Latitude,
            FROM `{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.{settings.CC_FEED_TABLE_ID}` 
            WHERE ProjectID = {project_id}
            QUALIFY ROW_NUMBER() OVER (PARTITION BY ProjectID ORDER BY sourceFileCreationTime DESC ) = 1"""

    elif source_type == "dodge":
        query = f"""SELECT * FROM `{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.{settings.DODGE_FEED_TABLE_ID}` 
        WHERE DRNumber = {project_id}
        QUALIFY ROW_NUMBER() OVER (PARTITION BY DRNumber ORDER BY sourceFileCreationTime DESC ) = 1"""
    
    # Execute the query and return the results as a DataFrame
    results = big_query_client.query_table(query=query, to_dataframe=True)

    if results.empty:
        raise ValueError(f"No data found for project ID {project_id} in source {source_type}") 
    else: 
        return results.iloc[0]

def test_same_project(project_1_data, project_2_data, project_1_source, project_2_source):
    
    p1_id, p2_id, distance_between_projects, match, reasoning = process_one_project_pair_deduplication(
        project_1_data,
        project_2_data,
        project_1_source,
        project_2_source
        ) 

    print(f"Distance: {distance_between_projects} miles, Match: {match}, Reasoning: {reasoning}")
    assert distance_between_projects < 0.5, "Distance between projects should be less than 0.5 miles"
    assert match == "match", "Projects should match"

def test_no_match_different_projects_distance(project_1_data, project_2_data, project_1_source, project_2_source):
    
    p1_id, p2_id, distance_between_projects, match, reasoning = process_one_project_pair_deduplication(
        project_1_data,
        project_2_data,
        project_1_source,
        project_2_source
        ) 

    print(f"Distance: {distance_between_projects} miles, Match: {match}, Reasoning: {reasoning}")
    assert distance_between_projects > 0.5, "Distance between projects should be more than 0.5 miles" 
    assert match == "no_match", "Projects should not match"
    assert "Distance (miles) between projects exceeds threshold:" in reasoning, "Reasoning should indicate that distance exceeds threshold"

def test_no_match_different_project_titles(project_1_data, project_2_data, project_1_source, project_2_source):
    
    p1_id, p2_id, distance_between_projects, match, reasoning = process_one_project_pair_deduplication(
        project_1_data,
        project_2_data,
        project_1_source,
        project_2_source
        ) 

    print(f"Distance: {distance_between_projects} miles, Match: {match}, Reasoning: {reasoning}")
    assert match == "no_match", "Projects should not match"
    assert "Titles" in reasoning and "match ratio" in reasoning, "Reasoning should indicate that titles do not match"

def test_no_match_different_project_details(project_1_data, project_2_data, project_1_source, project_2_source):
    
    p1_id, p2_id, distance_between_projects, match, reasoning = process_one_project_pair_deduplication(
        project_1_data,
        project_2_data,
        project_1_source,
        project_2_source
        ) 

    print(f"Distance: {distance_between_projects} miles, Match: {match}, Reasoning: {reasoning}")
    assert match == "no_match", "Projects should not match" 
    assert "Distance (miles) between projects exceeds threshold:" not in reasoning, "Reasoning should not indicate that distance exceeds threshold"
    assert "match ratio" not in reasoning, "Reasoning should indicate that titles should be somewhat simialr"

def test_unsure_projects(project_1_data, project_2_data, project_1_source, project_2_source):
    p1_id, p2_id, distance_between_projects, match, reasoning = process_one_project_pair_deduplication(
        project_1_data,
        project_2_data,
        project_1_source,
        project_2_source
        ) 

    print(f"Distance: {distance_between_projects} miles, Match: {match}, Reasoning: {reasoning}")
    assert match == "unsure", "Projects should be marked as unsure"

if __name__ == "__main__": 

    print("Test 1: Starting test for matching same project...\n")
    project_1 = fetch_project_from_bigquery(1007618369, big_query_client, "construct_connect")
    project_2 = fetch_project_from_bigquery(202500198521, big_query_client, "dodge")
    
    test_same_project(
        project_1_data=project_1,
        project_2_data=project_2, 
        project_1_source="construct_connect",
        project_2_source="dodge")
    print("\nTest #1 successfully completed.")

    print("------------------------------------------------------")

    print("Test 2: Starting test for different project with far distance...\n")
    project_1 = fetch_project_from_bigquery(1007228179, big_query_client, "construct_connect")
    project_2 = fetch_project_from_bigquery(202400333280, big_query_client, "dodge")

    test_no_match_different_projects_distance(
        project_1_data=project_1,
        project_2_data=project_2, 
        project_1_source="construct_connect",
        project_2_source="dodge") 

    print("\nTest 2 successfully completed.")

    print("------------------------------------------------------")

    print("Test 3: Starting test for different project with close distance and dissimilar titles...\n")
    project_1 = fetch_project_from_bigquery(1007152903, big_query_client, "construct_connect")
    project_2 = fetch_project_from_bigquery(202400291356, big_query_client, "dodge")

    test_no_match_different_project_titles(
        project_1_data=project_1,
        project_2_data=project_2, 
        project_1_source="construct_connect",
        project_2_source="dodge") 

    print("\nTest 3 successfully completed.")

    print("------------------------------------------------------")

    print("Test 4: Starting test for different project with close distance and similar titles...\n")

    project_1 = fetch_project_from_bigquery(1006750455, big_query_client, "construct_connect")
    project_2 = fetch_project_from_bigquery(202200749296, big_query_client, "dodge")

    test_no_match_different_project_details(
        project_1_data=project_1,
        project_2_data=project_2, 
        project_1_source="construct_connect",
        project_2_source="dodge") 

    print("\nTest 4 successfully completed.")

    print("------------------------------------------------------")

    print("Test 5: Starting test for group of duplicate projects...")

    duplicate_project_ids = [1007608639, 1007608638, 1007608637, 1007608636, 1007608634, 1007608633]
    query = f"""SELECT *, 
            `Addresses_Address`[SAFE_OFFSET(0)].Longitude AS Longitude,
            `Addresses_Address`[SAFE_OFFSET(0)].Latitude AS Latitude,
            FROM `{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.{settings.CC_FEED_TABLE_ID}` 
            WHERE ProjectID in UNNEST({duplicate_project_ids})
            QUALIFY ROW_NUMBER() OVER (PARTITION BY ProjectID ORDER BY sourceFileCreationTime DESC ) = 1"""
    
    results = big_query_client.query_table(query=query, to_dataframe=True)
    if results.empty:
        raise ValueError("No data found for project duplicates") 
    else: 
        projects = results

    for _, project_1 in projects.iterrows():
        for _, project_2 in projects.iterrows():
            if project_1['ProjectID'] != project_2['ProjectID']:

                test_same_project(
                    project_1_data=project_1,
                    project_2_data=project_2, 
                    project_1_source="construct_connect",
                    project_2_source="construct_connect")

    print("\nTest 5 successfully completed.")

    print("------------------------------------------------------")
    print("\nTest 6: Starting test unsure projects...")
    
    project_1 = pd.DataFrame({ 
        "ProjectID": [1007608639],
        "Title": ["Bridge Construction"],
        "Longitude": [-122.4194],
        "Latitude": [37.7749],
        "Valuation_Value": [5000000],
        "Details_Detail_Details": ["Construction of a new bridge over the river."],
    })

    project_2 = pd.DataFrame({ 
        "ProjectID": [1007608638],
        "Title": ["Bridge Construction"],
        "Longitude": [-122.4195],
        "Latitude": [37.7750],
        "Valuation_Value": [5000000],
        "Details_Detail_Details": ["Construction of a new bridge over the lake."],
    })

    test_unsure_projects(
        project_1_data=project_1.iloc[0],
        project_2_data=project_2.iloc[0], 
        project_1_source="construct_connect",
        project_2_source="construct_connect")
    
    print("\nTest 6 successfully completed.")

    print("------------------------------------------------------")
    print("All tests completed successfully.")
    print("------------------------------------------------------")


