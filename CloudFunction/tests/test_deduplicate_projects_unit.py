import os 
import sys 
import pandas as pd
from unittest.mock import Mock, patch, MagicMock
from google.cloud import bigquery 
import pytest 
import numpy as np
import json

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
    
from config import get_settings
from services import BigQueryManager, GCPCloudTaskClient, GCSFileManager
from deduplicate_projects_batch import deduplicate_projects_batch
from resolve_potential_duplicates import resolve_potential_duplicates

settings = get_settings()
BQ_CLIENT = BigQueryManager(dataset_id=settings.BIGQUERY_DATASET)

@pytest.fixture 
def mock_bq_client(): 
    return Mock(spec=BigQueryManager) 

@pytest.fixture 
def mock_task_client(): 
    return Mock(spec=GCPCloudTaskClient)

@pytest.fixture 
def mock_gcs_client(): 
    return Mock(spec=GCSFileManager)

@pytest.mark.parametrize(
    "test_id, project_1_id, project_2_id, project_1_source, project_2_source, file_path, source_file_creation_time, duplicate_task_calls, llm_match_response",
    [
        # Case 1: One CC project and one Dodge project which match (similar owners, title, within distance)
        (
            "cc_dodge_match",
            1007618369, 
            202500198521, 
            "construct_connect", 
            "dodge", 
            "Delta/1.4_DL_FBMSales_XML_20250523.xml", # File for Project 1
            "2025-05-23T06:41:13", # File creation time for Project 1
            1, # distance and title check passes, expect 1 task call
            "match", # expect LLM to return "match" for this pair
        ),
        # Case 2: One CC project and one Dodge project which do not match (far distance) 
        (
            "cc_dodge_no_match_far_distance",
            1007228179, 
            202400333280, 
            "construct_connect", 
            "dodge", 
            "Delta/1.4_DL_FBMSales_XML_20250311.xml",
            "2025-03-11T06:37:59", 
            0, # distance check fails, expect no task call
            None, # expect no LLM call as distance check fails         
        ),
        # Case 3: One CC project and one Dodge project which do not match (within distance, different titles)
        (
            "cc_dodge_no_match_different_title",
            1007152903,
            202400291356, 
            "construct_connect", 
            "dodge", 
            "Delta/1.4_DL_FBMSales_XML_20250410.xml", 
            "2025-04-10T06:42:57", 
            0, # title check fails, expect no task call
            None, # expect no LLM call as title check fails
        ), 
        # Case 4: One CC project and one CC project don't match (within distance, similar titles, but different details
        (
            "cc_dodge_no_match_different_project_details", 
            1006750455, 
            202200749296,
            "construct_connect", 
            "dodge", 
            "History/cmd_leads_files_5/1.4_Adhoc_DL_FBMSales_XML_20241009_266.xml", 
            "2025-02-06T05:42:37", 
            1, # distance and title check passes, expect 1 task call
            "no_match", # expect LLM to return "no_match" for this pair
        ), 
        # Case 5: Two CC projects which match (similar owners, within distance, different Bid Packages)
        (
            "cc_cc_match", 
            1007608638,
            1007608639, 
            "construct_connect", 
            "construct_connect",  
            "Delta/1.4_DL_FBMSales_XML_20250501.xml", 
            "2025-05-01T16:09:10", 
            1, 
            "match", 
        ), 
        # Case 6: Two CC projects which do not match 
        (
            "cc_cc_no_match", 
            1007608638, 
            1007618369, 
            "construct_connect", 
            "construct_connect", 
            "Delta/1.4_DL_FBMSales_XML_20250501.xml", 
            "2025-05-01T16:09:10", 
            0, # distance check fails, expect no task call
            None, # expect no LLM call as distance check fails
        ),
        # Case 7: Two Dodge projects which match (same owners, within distance, similar titles) 
        ( 
            "dodge_dodge_match",
            202300176510,
            202300019920,
            "dodge",
            "dodge",
            "History/Historical_50.xml",    
            "2025-03-25T20:18:18",
            1, 
            "match", 
        ),
        # Case 8: Dodge projects which do not match (exceed distance) 
        (
            "dodge_dodge_no_match",
            201900553175, 
            201900553169, 
            "dodge", 
            "dodge", 
            "History/Historical_61.xml", 
            "2025-03-25T20:18:24", 
            0, # distance and title check passes, expect 1 task call
            None, # expect LLM to return "no_match" for this pair due to different blocks
        ), 
        # Case 9: Dodge projects which match (within distance, similar titles, multiple owners)
        # Dodge project owners are swapped, checking to ensure that the deduplication logic can handle multiple owners
        (
            "dodge_dodge_match_multiple_owners",
            202500184502,
            202500184453,
            "dodge",
            "dodge",    
            "Delta/Unified_20250430.xml", 
            "2025-05-20T17:57:13", 
            1, 
            "match",
        ),
    ]
) 

@patch("deduplicate_projects_batch.invoke_cloud_function")
@patch("deduplicate_projects_batch.GCSFileManager")
@patch("resolve_potential_duplicates.big_query_client")
@patch("deduplicate_projects_batch.big_query_client")
@patch("deduplicate_projects_batch.GCPCloudTaskClient")
def test_deduplicate_projects_pair(mock_task_client, 
                                    mock_bq_client, 
                                    mock_bq_client_resolve_potential_duplicates,
                                    mock_gcs_client,
                                    mock_invoke_cloud_function,
                                    test_id, 
                                    project_1_id, 
                                    project_2_id, 
                                    project_1_source, 
                                    project_2_source,
                                    file_path, # applies to project in the deduplicate table, p1
                                    source_file_creation_time, # applies to project in the deduplicate table, p1
                                    duplicate_task_calls, 
                                    llm_match_response):

    # Populates temporary project deduplication table with the projects to process
    def fetch_project_for_deduplicate_table(project_id, source): 
        if source == "construct_connect": 
            query = f"""SELECT "1" as batch_id,
                            ProjectID as project_id, 
                            Title as ProjectTitle,
                            Addresses_Address [SAFE_OFFSET(0)].Latitude lat,
                            Addresses_Address [SAFE_OFFSET(0)].Longitude long,
                            cast(sourceFileCreationTime as string) as sourceFileCreationTime, 
                            "construct_connect" as source 
                            FROM `{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.{settings.CC_FEED_TABLE_ID}` 
                            WHERE ProjectID = {project_id}
                            QUALIFY ROW_NUMBER() OVER (PARTITION BY ProjectID ORDER BY sourceFileCreationTime DESC) = 1
                            LIMIT 1"""
        
        elif source == "dodge":
            query = f"""SELECT "1" as batch_id,
                            DRNumber as project_id, 
                            ProjectTitle as ProjectTitle,
                            Lat as lat,
                            Long as long,
                            cast(sourceFileCreationTime as string) as sourceFileCreationTime, 
                            "dodge" as source 
                            FROM `{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.{settings.DODGE_FEED_TABLE_ID}` 
                            WHERE DRNumber = {project_id}
                            QUALIFY ROW_NUMBER() OVER (PARTITION BY DRNumber ORDER BY sourceFileCreationTime DESC) = 1
                            LIMIT 1"""
                            
        df = CLIENT.query(query).to_dataframe()

        # Load into temporary table 
        table_id = f"{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.temp_projects_for_deduplication"
        df.to_gbq(table_id, if_exists="replace")

        # Rename columns to match expected 
        df_rename_columns = df.rename(columns={
            "project_id": "pfd_project_id",
            "ProjectTitle": "pfd_ProjectTitle",
            "lat": "pfd_lat",
            "long": "pfd_long",
            "source": "pdf_source"
        })

        return df_rename_columns

    # Mock the query side effect to return specific data or alter queries based on the input
    def query_side_effect(query, to_dataframe=False): 

        # Return Project 1 data as project_candidate in the project_for_deduplication table
        if """SELECT project_id as pfd_project_id, 
                    ProjectTitle as pfd_ProjectTitle,
                    lat as pfd_lat,
                    long as pfd_long,
                    cast(sourceFileCreationTime as string) sourceFileCreationTime,
                    data_source as pdf_source""" in query: 
            
            return fetch_project_for_deduplicate_table(project_1_id, project_1_source)

        # Modify query to fetch Project 2 data identifying duplicate projects in ConstructConnect or Dodge table 
        elif "ST_DISTANCE" in query: 
            
            # Remove the 30 DAY filter to allow for larger window check
            query = query.replace("30 DAY", "10000 DAY")

            # Replace actual table name with temporary table name
            query = query.replace(settings.PROJECTS_FOR_DEDUPLICATION_TABLE_ID, "temp_projects_for_deduplication")
            
            # Case where project_2_source is ConstructConnect and querying ConstructConnect data
            if project_2_source == "construct_connect" and "CC" in query: 
                
                # Add filter condition to only fetch Project 2 data
                substring = "AND project_id != ProjectID"
                insert_string = f""" and ProjectID = {project_2_id} """ 
                index_to_insert = query.find(substring)
                
                if index_to_insert == -1:
                    print("Substring not found in query.")
                    return CLIENT.query(query).to_dataframe() 
                
                # Add the condition
                new_query = query[:index_to_insert] + insert_string + query[index_to_insert:]

                # Return the modified query result
                return CLIENT.query(new_query).to_dataframe()
            
            # Case where project_2_source is Dodge and querying Dodge data
            elif project_2_source == "dodge" and "DD" in query: 

                # Add filter condition to only fetch Project 2 data
                substring = "AND project_id != DRNumber"
                insert_string = f""" and DRNumber = {project_2_id} """
                index_to_insert = query.find(substring)

                if index_to_insert == -1:
                    print("Substring not found in query.")
                    return CLIENT.query(query).to_dataframe()
                
                # Add the condition
                new_query = query[:index_to_insert] + insert_string + query[index_to_insert:]

                # Return the modified query result
                return CLIENT.query(new_query).to_dataframe() 
            
            else: 
                # Searching CC data for Dodge project or vice versa; return empty DataFrame to prevent further processing
                return pd.DataFrame()
            
        # Default case: query as normal 
        return CLIENT.query(query).to_dataframe() 
    
    def insert_rows(table_id, rows):
        return rows
    
    
    print(f"\n ----- Starting test: {test_id} ----- \n")

    CLIENT = bigquery.Client(project=settings.PROJECT_ID)

    # Apply the query side effect to alter query 
    mock_bq_client.query_table.side_effect = query_side_effect

    # Mock the insert_rows method to avoid writing to BigQuery 
    mock_bq_client_resolve_potential_duplicates.insert_rows.side_effect = insert_rows

    # Mock task client 
    mock_task_instance = MagicMock(spec=GCPCloudTaskClient)
    mock_task_client.return_value = mock_task_instance 
    return_task = Mock() 
    mock_task_instance.create_task.return_value = return_task 
    return_task.name = None

    # Mock GCS client
    mock_gcs_instance = MagicMock(spec=GCSFileManager)
    mock_gcs_client.return_value = mock_gcs_instance

    mock_request = Mock() 
    mock_data_dict = {
        "event": {
        "name": file_path,
        "timeCreated": source_file_creation_time,
        "bucket": "construct_connect_full_dump" if project_1_source == "construct_connect" else "dodge_full_dump", 
        "batch_id": "1", 
        } 
    }

    mock_request.get_json = lambda silent=True: mock_data_dict

    # Run the deduplicate_projects_batch function with the mock request
    response = deduplicate_projects_batch(mock_request)
     
    print("response:", json.dumps(response, indent=2))

    # Assert duplicate task calls: = 1 if projects passed distance and title check, else 0
    number_task_calls = mock_task_instance.create_task.call_count
    assert number_task_calls == duplicate_task_calls, f"Expected {duplicate_task_calls} task calls, but got {number_task_calls}"

    # Projects passed distance and title check; pass to LLM and check result 
    if number_task_calls > 0:

        called_args = mock_task_instance.create_task.call_args 
        args, kwargs = called_args
        
        # Fetch payload generated from the create_task call
        payload = kwargs.get("payload")
        
        mock_request = Mock() 
        mock_request.get_json = lambda silent=True: payload

        # Run the resolve_potential_duplicates function with the mock request
        response = resolve_potential_duplicates(mock_request)

        print("resonse:", json.dumps(response, indent=2))

        # Assert LLM created result 
        assert mock_bq_client_resolve_potential_duplicates.insert_rows.call_count == 1

        # Fetch the rows_to_insert created
        args, kwargs = mock_bq_client_resolve_potential_duplicates.insert_rows.call_args
        rows_inserted = args[1]

        # Fetch match result from insert_rows method 
        match_result = rows_inserted[0].get('llm_result', '')

        # Assert the match result is as expected
        assert match_result == llm_match_response, f"Expected '{llm_match_response}', but got '{match_result}'"



# To run specific tests: pytest -s tests/test_deduplicate_projects_unit.py [-k "test_id"]