import json
import os
import sys
import uuid
from datetime import datetime, timezone
import unittest
from unittest.mock import MagicMock, Mock, patch

import warnings
warnings.filterwarnings("ignore", category=PendingDeprecationWarning)

import pandas as pd
import pytest
from google.cloud import bigquery
import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pandas as pd
import pytest
from functions_framework import create_app

# Get the directory of the current script
current_dir = os.path.dirname(os.path.abspath(__file__))

# Move one level up to the parent directory
parent_dir = os.path.abspath(os.path.join(current_dir, os.pardir))

# Add the parent directory to sys.path
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from utils.batch_upsert_leads_utils import CREATE_UNIQUE_COMBINATION_QUERY
from batch_upsert_leads import batch_upsert_leads, get_unique_combinations
from config import get_settings
from services import BigQueryManager

settings = get_settings()
big_query_client = BigQueryManager(dataset_id=settings.BIGQUERY_DATASET)

sales_profile_temp = 'unit_test_sales_profile_temp'
project_relevance_table = 'unit_test_project_relevance'
cc_table = 'unit_test_cc_feed'

def infer_bq_schema_from_df(df):
    import numpy as np
    from google.cloud import bigquery

    type_mapping = {
        'int64': 'INTEGER',
        'float64': 'FLOAT',
        'bool': 'BOOLEAN',
        'object': 'STRING',
        'datetime64[ns]': 'TIMESTAMP'
    }

    schema = []
    for col in df.columns:
        dtype = str(df[col].dtype)
        bq_type = type_mapping.get(dtype, 'STRING')
        schema.append(bigquery.SchemaField(col, bq_type))

    return schema

def create_test_tables(data,table_id):

    df = pd.DataFrame(data)
    schema = infer_bq_schema_from_df(df)
    job_config = bigquery.LoadJobConfig(
                    create_disposition=bigquery.CreateDisposition.CREATE_IF_NEEDED,
                    write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
                    schema=schema
                )
    big_query_client.load_from_dataframe(
        table_id=table_id,
        dataframe=df,
        job_config=job_config

    )

cc_data = [
        {
            "ProjectID": 1323947,
            "sourceFileCreationTime": "2025-04-25T06:42:02",
            "sourceFile": "test_file.xml"
        }
    ]
create_test_tables(cc_data,cc_table)

class TestLeadAssignment(unittest.TestCase):

    def simulate_bigquery_filter(self, project_data: list) -> list:
        """
        Simulates the BigQuery `QUALIFY ROW_NUMBER() OVER (PARTITION BY project_id, search_id ORDER BY time_created DESC, distance ASC, modified_on DESC) = 1`
        This function filters the records to retain the top-ranked row per (project_id, search_id) based on:
        - Newest time_created (DESC)
        - Closest distance (ASC)
        - Most recently modified_on (DESC)
        """
        if not project_data:
            return []

        df = pd.DataFrame(project_data)

        # Convert datetime fields for proper sorting
        df['time_created'] = pd.to_datetime(df['time_created'], errors='coerce')
        df['modified_on'] = pd.to_datetime(df['modified_on'], errors='coerce')
        df['distance'] = pd.to_numeric(df['distance'], errors='coerce')

        # Sort and rank using row_number equivalent
        df['row_rank'] = (
            df.sort_values(
                by=['time_created', 'distance', 'modified_on'],
                ascending=[False, True, False]
            )
            .groupby(['project_id', 'search_id'], group_keys=False)
            .cumcount()
        )

        # Select only top row (i.e., row_number = 1)
        top_rows = df[df['row_rank'] == 0].drop(columns='row_rank')

        return top_rows.to_dict(orient='records')

    def test_1_single_salesperson_assigned_via_closest_branch(self):
        """
        Tests that a salesperson assigned to two branches gets exactly one lead
        for a project, associated with the closest branch.
        """
        print("Test 1: salesperson assigned to two branches gets exactly one lead for a project, associated with the closest branch....\n")
        # 1. ARRANGE: Define the raw data as it exists in BigQuery (2 rows)
         # Get project relevance for delta file.
        raw_bq_data_two_rows = [
            {
                "project_id": 1323947,
                "relevance": "Moderate",
                "reasoning": "The project involves an addition and demolition of a community center, which aligns with potential opportunities. The presence of \u0027Acoustical Ceilings\u0027 and \u0027Ceiling Suspension Systems\u0027 in the materials list, along with the search term \u0027CEILINGS\u0027, indicates a potential need for relevant products. However, without a specific brand match or more detailed information, the relevance is moderate.",
                "search_id": "8176f317-2c4e-f011-8779-000d3a307462",
                "territory_id": "c4f13b06-f4b3-ec11-9840-000d3a58fb6e",
                "time_created": "2025-04-25T06:42:02",
                "source": "construct_connect",
                "modified_on": "2025-05-12 20:19:23.910763 UTC",
                "distance": 5.81,
                "confidence": 0.7,
                "materials_valuation": None
            }, {
                "project_id": 1323947,
                "relevance": "Moderate",
                "reasoning": "The project involves an addition and demolition to a community center, which aligns with commercial projects. The presence of \u0027Acoustical Ceilings\u0027 and \u0027Ceiling Suspension Systems\u0027 in the material list, along with the search term \u0027CEILINGS\u0027, indicates a potential need for relevant products. The project valuation of $4.5 million suggests a significant undertaking. However, no specific brands like Armstrong, USG, or CertainTeed are mentioned, which lowers the relevance slightly.",
                "search_id": "8176f317-2c4e-f011-8779-000d3a307462",
                "territory_id": "c2f13b06-f4b3-ec11-9840-000d3a58fb6e",
                "time_created": "2025-04-25T06:42:02",
                "source": "construct_connect",
                "modified_on": "2025-05-12 15:51:51.876573 UTC",
                "distance": 35.39,
                "confidence": 0.75,
                "materials_valuation": None
            }
        ]

        create_test_tables(raw_bq_data_two_rows,project_relevance_table)       
        # Mock the settings object needed by the function
        mock_settings = Mock()
        mock_settings.DM_DEFAULT_SALES_REP_ID = "1d129d97-5e6b-e911-a822-000d3a315bf6"
        mock_settings.DM_SALES_PROFILE_ID = "fbm_salesprofile"

        # Mock the Dynamics client
        mock_dynamics_client = Mock()

        # Mock the sales profile data returned by the Dynamics client.
        # "Steve" is assigned to the same search but for two different branches.
        sales_profiles_data = [

                {                    
                    "_ownerid_value": "909dcabd-fdcf-ea11-a812-000d3a5a78d3",
                    "fbm_salesprofileid": "3e17850f-e410-f011-9988-000d3a307462",
                    "_fbm_branchid_value": "c4f13b06-f4b3-ec11-9840-000d3a58fb6e",
                    "fbm_name": "Steve",
                    "_fbm_searchid_value": "8176f317-2c4e-f011-8779-000d3a307462"
                },
                {                   
                    "_ownerid_value": "909dcabd-fdcf-ea11-a812-000d3a5a78d3",
                    "fbm_salesprofileid": "edce8bc2-e610-f011-9988-000d3a307462",
                    "_fbm_branchid_value": "c2f13b06-f4b3-ec11-9840-000d3a58fb6e",
                    "fbm_name": "Steve",
                    "_fbm_searchid_value": "8176f317-2c4e-f011-8779-000d3a307462"
                }
            
        ]
        mock_dynamics_client.get_data.return_value = sales_profiles_data

        create_test_tables(sales_profiles_data,sales_profile_temp)
       
    #    # 2. ACT
        sourcefile_filter = f"AND cc.sourceFile = 'test_file.xml'"
        create_unique_combination_query = CREATE_UNIQUE_COMBINATION_QUERY.format(
            data_set = settings.BIGQUERY_DATASET,
            project_relevance_table = project_relevance_table,
            searches_table = settings.SEARCHES_TABLE_ID,
            sales_profile_temp = sales_profile_temp,
            default_sales_rep_id = settings.DM_DEFAULT_SALES_REP_ID,
            cc_table = cc_table,
            sourcefile_filter = sourcefile_filter,
            search_id_filter = ''
        )

        
        # create_unique_combination_query: This query retrieves project relevance data,
        # appends 'core' search rows, and generates unique project_id-search_id-sales_rep combinations.
        result = big_query_client.query_table(query=create_unique_combination_query)

        # 3. ASSERT

        # Assert that exactly one lead combination was created
        self.assertEqual(len(result), 1, "Should create exactly one lead.")
        # Assert that the lead is for the correct salesperson and project
        lead = result[0]


        self.assertEqual(lead["sales_rep_id"], "909dcabd-fdcf-ea11-a812-000d3a5a78d3", "Lead should be assigned to Steve.")
        self.assertEqual(lead["project_id"], 1323947, "Lead should be for the correct project.")
        self.assertEqual(lead["search_id"], "8176f317-2c4e-f011-8779-000d3a307462", "Lead should be associated with the correct search.")

        self.assertEqual(lead["territory_id"], "c4f13b06-f4b3-ec11-9840-000d3a58fb6e", "Lead should be assigned to the closest branch.")
        # The assertion that only one lead is created implicitly confirms it's via the closest branch,
        # because 'branch-1-id' was the only territory provided in the input data.
        
        print(f"\nGenerated Lead Combination: {dict(lead)}\n\nTest 1 passed: Steve received exactly one lead for the project via the closest branch.")
        print('----------- END OF TEST 1 -----------')
        print("\n\n")


    # --- TEST CASE TO CAPTURE FLAWED BEHAVIOR ---
    def test_2_salesperson_for_farther_branch_is_missed_due_to_pre_filtering(self):
        """
        A salesperson ("Cody") should also assigned to a lead for a farther branch
    
        """
        print("""Test 2: A salesperson ("Cody") should also assigned to a lead for a farther branch.""")
        # 1. ARRANGE: Data is the same, showing relevance to two branches.
        raw_bq_data_two_rows = [
            {
                "project_id": 1323947,
                "relevance": "Moderate",
                "reasoning": "The project involves an addition and demolition of a community center, which aligns with potential opportunities. The presence of \u0027Acoustical Ceilings\u0027 and \u0027Ceiling Suspension Systems\u0027 in the materials list, along with the search term \u0027CEILINGS\u0027, indicates a potential need for relevant products. However, without a specific brand match or more detailed information, the relevance is moderate.",
                "search_id": "8176f317-2c4e-f011-8779-000d3a307462",
                "territory_id": "c4f13b06-f4b3-ec11-9840-000d3a58fb6e",
                "time_created": "2025-04-25T06:42:02",
                "source": "construct_connect",
                "modified_on": "2025-05-12 20:19:23.910763 UTC",
                "distance": 5.81,
                "confidence": 0.7,
                "materials_valuation": None
            }, {
                "project_id": 1323947,
                "relevance": "Moderate",
                "reasoning": "The project involves an addition and demolition to a community center, which aligns with commercial projects. The presence of \u0027Acoustical Ceilings\u0027 and \u0027Ceiling Suspension Systems\u0027 in the material list, along with the search term \u0027CEILINGS\u0027, indicates a potential need for relevant products. The project valuation of $4.5 million suggests a significant undertaking. However, no specific brands like Armstrong, USG, or CertainTeed are mentioned, which lowers the relevance slightly.",
                "search_id": "8176f317-2c4e-f011-8779-000d3a307462",
                "territory_id": "c2f13b06-f4b3-ec11-9840-000d3a58fb6e",
                "time_created": "2025-04-25T06:42:02",
                "source": "construct_connect",
                "modified_on": "2025-05-12 15:51:51.876573 UTC",
                "distance": 35.39,
                "confidence": 0.75,
                "materials_valuation": None
            }
        ]
        
        
        create_test_tables(raw_bq_data_two_rows,project_relevance_table)
        mock_settings = Mock()
        mock_settings.DM_DEFAULT_SALES_REP_ID = "1d129d97-5e6b-e911-a822-000d3a315bf6"
        mock_settings.DM_SALES_PROFILE_ID = "fbm_salesprofile"

        # Mock the Dynamics client
        mock_dynamics_client = Mock()

        # Mock salesperson data: "Steve" covers the close branch, "Cody" covers the far one.
        sales_profiles_data = {
            "value": [
                {
                    "_ownerid_value": "909dcabd-fdcf-ea11-a812-000d3a5a78d3", # Steve's ID
                    "_fbm_branchid_value": "c4f13b06-f4b3-ec11-9840-000d3a58fb6e", # Closer Branch
                    "_fbm_searchid_value": "8176f317-2c4e-f011-8779-000d3a307462"
                },
                {
                    "_ownerid_value": "909dcabd-fdcf-ea11-a812-000d3a5a78d3", # Steve's ID
                    "_fbm_branchid_value": "c2f13b06-f4b3-ec11-9840-000d3a58fb6e", # Closer Branch
                    "_fbm_searchid_value": "8176f317-2c4e-f011-8779-000d3a307462"
                },
                {
                    "_ownerid_value": "c0d4a11e-c0d4-c0d4-c0d4-c0d4a11ec0d4", # Cody's ID
                    "_fbm_branchid_value": "c2f13b06-f4b3-ec11-9840-000d3a58fb6e", # Farther Branch
                    "_fbm_searchid_value": "8176f317-2c4e-f011-8779-000d3a307462"
                }
            ]
        }

        create_test_tables(sales_profiles_data['value'],sales_profile_temp)
        mock_dynamics_client.get_data.return_value = sales_profiles_data

        # 2. ACT
        sourcefile_filter = f"AND cc.sourceFile = 'test_file.xml'"
        create_unique_combination_query = CREATE_UNIQUE_COMBINATION_QUERY.format(
            data_set = settings.BIGQUERY_DATASET,
            project_relevance_table = project_relevance_table,
            searches_table = settings.SEARCHES_TABLE_ID,
            sales_profile_temp = sales_profile_temp,
            default_sales_rep_id = settings.DM_DEFAULT_SALES_REP_ID,
            cc_table = cc_table,
            sourcefile_filter = sourcefile_filter,
            search_id_filter = ''
        )

        
        # create_unique_combination_query: This query retrieves project relevance data,
        # appends 'core' search rows, and generates unique project_id-search_id-sales_rep combinations.
        result = big_query_client.query_table(query=create_unique_combination_query)
       

        # 3. ASSERT: Confirm the flaw
        
        # 2 lead should be created in total (one for Steve and another for cody).
        self.assertEqual(len(result), 2, "Should create 2 lead for the closest branch's salesperson.")
        
        
        #confirm that lead was created for Steve.
        cody_leads = [lead for lead in result if lead['sales_rep_id'] == '909dcabd-fdcf-ea11-a812-000d3a5a78d3']
        self.assertEqual(len(cody_leads), 1, "CONFIRMED FLAW: Steve should receive a lead.")
        
        
        #confirm that lead was created for Cody.
        cody_leads = [lead for lead in result if lead['sales_rep_id'] == 'c0d4a11e-c0d4-c0d4-c0d4-c0d4a11ec0d4']
        self.assertEqual(len(cody_leads), 1, "CONFIRMED FLAW: Cody should receive a lead.")
        result = [ dict(row) for row in result]
        print(f"\nGenerated Lead Combination: {result}\n\nTest 2 passed: Confirmed that salesperson for farther branch is not missed.")

        print('----------- END OF TEST 2 -----------')

    def test_3_salesperson_assigned_to_two_equidistant_branches(self):
        """
        Scenario: A project is exactly the same distance from two branches.
        Assertion: The test confirms predictable tie-breaking behavior , or another deterministic rule.
        """
        print("Test 3: Salesperson assigned to two equidistant branches, testing tie-breaking behavior...\n")

        raw_bq_data_two_rows = [
            {
                "project_id": 1323947,
                "relevance": "Moderate",
                "reasoning": "The project involves an addition and demolition of a community center, which aligns with potential opportunities. The presence of \u0027Acoustical Ceilings\u0027 and \u0027Ceiling Suspension Systems\u0027 in the materials list, along with the search term \u0027CEILINGS\u0027, indicates a potential need for relevant products. However, without a specific brand match or more detailed information, the relevance is moderate.",
                "search_id": "8176f317-2c4e-f011-8779-000d3a307462",
                "territory_id": "c4f13b06-f4b3-ec11-9840-000d3a58fb6e",
                "time_created": "2025-04-25T06:42:02",
                "source": "construct_connect",
                "modified_on": "2025-05-12 20:19:23.910763 UTC",
                "distance": 5.81,
                "confidence": 0.7,
                "materials_valuation": None
            }, {
                "project_id": 1323947,
                "relevance": "Moderate",
                "reasoning": "The project involves an addition and demolition to a community center, which aligns with commercial projects. The presence of \u0027Acoustical Ceilings\u0027 and \u0027Ceiling Suspension Systems\u0027 in the material list, along with the search term \u0027CEILINGS\u0027, indicates a potential need for relevant products. The project valuation of $4.5 million suggests a significant undertaking. However, no specific brands like Armstrong, USG, or CertainTeed are mentioned, which lowers the relevance slightly.",
                "search_id": "8176f317-2c4e-f011-8779-000d3a307462",
                "territory_id": "c2f13b06-f4b3-ec11-9840-000d3a58fb6e",
                "time_created": "2025-04-25T06:42:02",
                "source": "construct_connect",
                "modified_on": "2025-05-12 15:51:51.876573 UTC",
                "distance": 5.81,
                "confidence": 0.7,
                "materials_valuation": None
            }
        ]
        create_test_tables(raw_bq_data_two_rows,project_relevance_table)
        mock_settings = Mock()
        mock_settings.DM_DEFAULT_SALES_REP_ID = "1d129d97-5e6b-e911-a822-000d3a315bf6"
        mock_settings.DM_SALES_PROFILE_ID = "fbm_salesprofile"

        mock_dynamics_client = Mock()

        # Steve covers both branches
        sales_profiles_data = {
            "value": [
                {
                    "_ownerid_value": "909dcabd-fdcf-ea11-a812-000d3a5a78d3", # Steve's ID
                    "_fbm_branchid_value": "c4f13b06-f4b3-ec11-9840-000d3a58fb6e", 
                    "_fbm_searchid_value": "8176f317-2c4e-f011-8779-000d3a307462"
                },
                {
                    "_ownerid_value": "909dcabd-fdcf-ea11-a812-000d3a5a78d3", # Steve's ID
                    "_fbm_branchid_value": "c2f13b06-f4b3-ec11-9840-000d3a58fb6e", 
                    "_fbm_searchid_value": "8176f317-2c4e-f011-8779-000d3a307462"
                }
            ]
        }
        create_test_tables(sales_profiles_data['value'],sales_profile_temp)
        mock_dynamics_client.get_data.return_value = sales_profiles_data

        sourcefile_filter = f"AND cc.sourceFile = 'test_file.xml'"
        create_unique_combination_query = CREATE_UNIQUE_COMBINATION_QUERY.format(
            data_set = settings.BIGQUERY_DATASET,
            project_relevance_table = project_relevance_table,
            searches_table = settings.SEARCHES_TABLE_ID,
            sales_profile_temp = sales_profile_temp,
            default_sales_rep_id = settings.DM_DEFAULT_SALES_REP_ID,
            cc_table = cc_table,
            sourcefile_filter = sourcefile_filter,
            search_id_filter = ''
        )

        
        # create_unique_combination_query: This query retrieves project relevance data,
        # appends 'core' search rows, and generates unique project_id-search_id-sales_rep combinations.
        result = big_query_client.query_table(query=create_unique_combination_query)
       


        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["territory_id"], "c4f13b06-f4b3-ec11-9840-000d3a58fb6e", "Should tie-break to latest modified_on of project_relevance record")
        print(f"\nGenerated Lead Combination: {dict(result[0])}\n\nTest 3 passed: Tie-breaking logic consistently selects latest modified_on of project_relevance record.")
        print('----------- END OF TEST 3 -----------\n\n')

    def test_4_no_lead_generated_if_outside_radius(self):
    # The following test case will fail because the 60-mile radius logic is not implemented in the batch_upsert_lead function.
    # The find_nearby_branch_haversine function (from send_project_to_queue) ensures that branches are assigned to projects only if they are within a 60-mile radius.
        """
        Scenario: Project is outside 60-mile radius for all branches of the search profile.
        Assertion: No lead should be created for that salesperson.
        """
        print("Test 4: No lead is generated if project is beyond 60 miles from all branch territories...\n")

        raw_bq_data = [
            {
                "project_id": 1323947,
                "relevance": "Moderate",
                "reasoning": "The project involves an addition and demolition of a community center, which aligns with potential opportunities. The presence of \u0027Acoustical Ceilings\u0027 and \u0027Ceiling Suspension Systems\u0027 in the materials list, along with the search term \u0027CEILINGS\u0027, indicates a potential need for relevant products. However, without a specific brand match or more detailed information, the relevance is moderate.",
                "search_id": "8176f317-2c4e-f011-8779-000d3a307462",
                "territory_id": "c4f13b06-f4b3-ec11-9840-000d3a58fb6e",
                "time_created": "2025-04-25T06:42:02",
                "source": "construct_connect",
                "modified_on": "2025-05-12 20:19:23.910763 UTC",
                "distance": 75.81,
                "confidence": 0.7,
                "materials_valuation": None
            }
        ]
        create_test_tables(raw_bq_data,project_relevance_table)
        mock_settings = Mock()
        mock_settings.DM_DEFAULT_SALES_REP_ID = "1d129d97-5e6b-e911-a822-000d3a315bf6"
        mock_settings.DM_SALES_PROFILE_ID = "fbm_salesprofile"

        mock_dynamics_client = Mock()

        # Steve is assigned to the branch, but it's out of range
        sales_profiles_data = {
            "value": [
                {
                    "_ownerid_value": "909dcabd-fdcf-ea11-a812-000d3a5a78d3", # Steve's ID
                    "_fbm_branchid_value": "c4f13b06-f4b3-ec11-9840-000d3a58fb6e",
                    "_fbm_searchid_value": "8176f317-2c4e-f011-8779-000d3a307462"
                }
            ]
        }
        create_test_tables(sales_profiles_data['value'],sales_profile_temp)

        mock_dynamics_client.get_data.return_value = sales_profiles_data

        sourcefile_filter = f"AND cc.sourceFile = 'test_file.xml'"
        create_unique_combination_query = CREATE_UNIQUE_COMBINATION_QUERY.format(
            data_set = settings.BIGQUERY_DATASET,
            project_relevance_table = project_relevance_table,
            searches_table = settings.SEARCHES_TABLE_ID,
            sales_profile_temp = sales_profile_temp,
            default_sales_rep_id = settings.DM_DEFAULT_SALES_REP_ID,
            cc_table = cc_table,
            sourcefile_filter = sourcefile_filter,
            search_id_filter = ''
        )
        # create_unique_combination_query: This query retrieves project relevance data,
        # appends 'core' search rows, and generates unique project_id-search_id-sales_rep combinations.
        result = big_query_client.query_table(query=create_unique_combination_query)
       
        self.assertEqual(result, [], "Should not generate any lead since project is out of range.")
        print("Test 4 passed: No lead generated when project is beyond 60-mile cutoff.")
        print('----------- END OF TEST 4 -----------\n\n')

        big_query_client.delete_table(project_relevance_table)
        big_query_client.delete_table(sales_profile_temp)
        big_query_client.delete_table(cc_table)


if __name__ == "__main__":
    unittest.main()
