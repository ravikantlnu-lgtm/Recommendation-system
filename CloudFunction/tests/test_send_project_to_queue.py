import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, call, patch

import numpy as np
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

from config import get_settings

# Import the Cloud Function and the specific function to test
from send_relevent_project_to_queue import (
    project_search_to_task_queue,
    send_projects_to_queue,
)
from services import (  # Assuming GCPCloudTaskClient is in services
    BigQueryManager,
    GCPCloudTaskClient,
)

settings = get_settings()
# Keep BigQueryManager instance for potential setup if needed, but mock its methods during tests
big_query_client = BigQueryManager(dataset_id=settings.BIGQUERY_DATASET)

# --- Test Data Fixtures ---


@pytest.fixture
def mock_settings():
    """Mock settings object."""
    settings = Mock()
    settings.PROJECT_ID = "test-project"
    settings.BIGQUERY_DATASET = "test_dataset"
    settings.PROJECT_RELEVANCE_TABLE_ID = "project_relevance"
    settings.ASSIGNED_SEARCH_TABLE_ID = "assigned_search"
    settings.CC_FEED_TABLE_ID = "cc_feed"
    settings.TERRITORIES_TABLE_ID = "territories"
    settings.SEARCHES_TABLE_ID = "searches"
    settings.SEARCH_TERRITORY_TABLE_ID = "search_territory_map"
    settings.CLOUD_TASK_LOCATION = "us-central1"
    settings.CLOUD_TASK_SEND_PROJECT_TO_QUEUE_QUEUE = "test-queue"
    settings.WORKFLOW_INVOCATION_SA = "test-sa@example.com"
    settings.WORKFLOW_INVOCATION_LOCATION = "us-central1"
    settings.WORKFLOW_INVOCATION_NAME = "test-workflow"
    settings.RADIUS_MILES = 60
    settings.MAX_BRANCHES = 5
    settings.MAX_WORKERS = 5
    return settings


@pytest.fixture
def mock_bq_client():
    """Mock BigQueryManager."""
    return Mock(spec=BigQueryManager)


@pytest.fixture
def mock_task_client():
    """Mock GCPCloudTaskClient."""
    return Mock(spec=GCPCloudTaskClient)


# --- Helper Function ---
def create_project_candidate_df(
    project_id, creation_time_str, assigned_branches=np.nan
):
    """Creates a sample project candidate DataFrame."""
    return pd.DataFrame(
        [
            {
                "ProjectID": project_id,
                "sourceFileCreationTime": creation_time_str,
                "Longitude": -75.0,
                "Latitude": 40.0,
                "assigned_branches": assigned_branches,  # Use np.nan for no branches
            }
        ]
    )


# --- Test Cases for project_search_to_task_queue ---

# Define common parameters
TEST_FILE_PATH = "delta/test_file.xml"

# Use a fixed, timezone-aware datetime string, then parse it
RAW_TIME_STR = "2025-04-21T10:00:00.000Z"
PARSED_TIME = datetime.fromisoformat(RAW_TIME_STR)

EXPECTED_TIME =  datetime.fromisoformat(RAW_TIME_STR).isoformat(timespec='seconds')
WORKFLOW_URL = f"https://workflowexecutions.googleapis.com/v1/projects/test-project/locations/us-central1/workflows/test-workflow/executions"

SEARCH_MATERIALS_DF = pd.DataFrame(
    {
        "search_id": ["S1", "S2"],
        "name": ["S1", "S2"],
        "division": ["D1", "D2"],
        "material": ["M1", "M2"],
        "code": ["C1", "C2"],
    }
)

@pytest.mark.parametrize(
    "test_id, project_candidates_df, search_id_ls, search_materials_df, processed_projects, non_related_searches, expected_calls, expected_project_search_cnt",
    [
        # Case 1: No branches, skip (already processed)
        (
            "no_branch_skip_processed",
            create_project_candidate_df("P1", PARSED_TIME),
            [{"search_id": "S1", "territory_id": None}],
            SEARCH_MATERIALS_DF,
            {("P1", "S1", None, PARSED_TIME)},  # Processed
            set(),
            [],  # No calls expected
            0, # Expected processed projects
        ),
        # Case 2: No branches, skip (non-related)
        (
            "no_branch_skip_non_related",
            create_project_candidate_df("P1", PARSED_TIME),
            [{"search_id": "S1", "territory_id": None}],
            SEARCH_MATERIALS_DF,
            set(),
            {("P1", "S1", PARSED_TIME)},  # Non-related
            [],  # No calls expected
            0,
        ),
        # Case 3: No branches, search has territory, skip
        (
            "no_branch_search_territory_skip",
            create_project_candidate_df("P1", PARSED_TIME),
            [{"search_id": "S1", "territory_id": "T1"}],  # Search has territory
            SEARCH_MATERIALS_DF,
            set(),
            set(),
            [],  # No calls expected
            0,
        ),
        # Case 4: No branches, search no territory, process
        (
            "no_branch_no_search_territory_process",
            create_project_candidate_df("P1", PARSED_TIME),
            [{"search_id": "S1", "territory_id": None}],  # Search has no territory
            SEARCH_MATERIALS_DF,
            set(),
            set(),
            [  # Expect one call to process_project_without_territory
                call(
                    url=WORKFLOW_URL,
                    payload={
                        "project_id": "P1",
                        "time_created": EXPECTED_TIME,
                        "search_id": "S1",
                        "territory_id": [
                            {"territory_id": None, "distance_from_territory": None}
                        ],
                        "distance_from_territory": None,
                        "territory_idx": None,
                        "search_materials_json":  """{"search_id":{"0":"S1"},"name":{"0":"S1"},"division":{"0":"D1"},"material":{"0":"M1"},"code":{"0":"C1"}}""",
                        "assign_queue": "send_project_to_queue",
                        "request_type": None,
                    },
                )
            ],
            1,
        ),
        # Case 5: Branches exist, all skip (processed/non-related)
        (
            "branch_all_skip",
            create_project_candidate_df(
                "P1",
                PARSED_TIME,
                assigned_branches=[
                    {"territory_id": "T1", "distance": 10},
                    {"territory_id": "T2", "distance": 20},
                ],
            ),
            [{"search_id": "S1", "territory_id": None}],
            SEARCH_MATERIALS_DF,
            {("P1", "S1", "T1", PARSED_TIME)},  # T1 processed
            {("P1", "S1", PARSED_TIME)},  # Covers T2 as non-related for the search
            [],  # No calls expected
            0,
        ),
        # Case 6: Branches exist, search has territory, no matching *processable* branch, skip
        (
            "branch_search_territory_no_match_skip",
            create_project_candidate_df(
                "P1",
                PARSED_TIME,
                assigned_branches=[
                    {"territory_id": "T1", "distance": 10},
                    {"territory_id": "T2", "distance": 20},
                ],
            ),
            [{"search_id": "S1", "territory_id": "T1"}],  # Search requires T1
            SEARCH_MATERIALS_DF,
            {("P1", "S1", "T1", PARSED_TIME)},  # T1 is processed, so not processable
            set(),  # T2 is processable but doesn't match search territory
            [],  # No calls expected
            0,
        ),
        # Case 7: Branches exist, search has territory, matching processable branch, process
        (
            "branch_search_territory_match_process",
            create_project_candidate_df(
                "P1",
                PARSED_TIME,
                assigned_branches=[
                    {"territory_id": "T1", "distance": 10},
                    {"territory_id": "T2", "distance": 20},
                ],
            ),
            [{"search_id": "S1", "territory_id": "T1"}],  # Search requires T1
            SEARCH_MATERIALS_DF,
            set(),  # T1 is processable
            set(),  # T2 is processable
            [  # Expect one call to process_project_with_territories
                call(
                    url=WORKFLOW_URL,
                    payload={
                        "project_id": "P1",
                        "time_created": EXPECTED_TIME,
                        "search_id": "S1",
                        # Only the matching territory should be sent
                        "territory_id": [
                            {"territory_id": "T1", "distance_from_territory": 10}
                        ],
                        "distance_from_territory": None,
                        "territory_idx": None,
                        "search_materials_json":  """{"search_id":{"0":"S1"},"name":{"0":"S1"},"division":{"0":"D1"},"material":{"0":"M1"},"code":{"0":"C1"}}""",
                        "assign_queue": "send_project_to_queue",
                        "request_type": None,
                    },
                )
            ],
            1,
        ),
        # Case 8: Branches exist, search no territory, some processable, process
        (
            "branch_no_search_territory_some_processable_process",
            create_project_candidate_df(
                "P1",
                PARSED_TIME,
                assigned_branches=[
                    {"territory_id": "T1", "distance": 10},
                    {"territory_id": "T2", "distance": 20},
                ],
            ),
            [{"search_id": "S1", "territory_id": None}],  # Search has no territory
            SEARCH_MATERIALS_DF,
            {("P1", "S1", "T1", PARSED_TIME)},  # T1 processed
            set(),  # T2 is processable
            [  # Expect one call to process_project_with_territories (only with T2)
                call(
                    url=WORKFLOW_URL,
                    payload={
                        "project_id": "P1",
                        "time_created": EXPECTED_TIME,
                        "search_id": "S1",
                        "territory_id": [
                            {"territory_id": "T2", "distance_from_territory": 20}
                        ],
                        "distance_from_territory": None,
                        "territory_idx": None,
                        "search_materials_json":  """{"search_id":{"0":"S1"},"name":{"0":"S1"},"division":{"0":"D1"},"material":{"0":"M1"},"code":{"0":"C1"}}""",
                        "assign_queue": "send_project_to_queue",
                        "request_type": None,
                    },
                )
            ],
            1,
        ),
        # Case 9: Multiple searches, one processed, one not
        (
            "multiple_searches_mixed",
            create_project_candidate_df("P1", PARSED_TIME),
            [
                {"search_id": "S1", "territory_id": None},
                {"search_id": "S2", "territory_id": None},
            ],
            SEARCH_MATERIALS_DF,
            {("P1", "S1", None, PARSED_TIME)},  # S1 processed
            set(),
            [  # Expect call only for S2
                call(
                    url=WORKFLOW_URL,
                    payload={
                        "project_id": "P1",
                        "time_created": EXPECTED_TIME,
                        "search_id": "S2",
                        "territory_id": [
                            {"territory_id": None, "distance_from_territory": None}
                        ],
                        "distance_from_territory": None,
                        "territory_idx": None,
                        "search_materials_json": """{"search_id":{"0":"S2"},"name":{"0":"S2"},"division":{"0":"D2"},"material":{"0":"M2"},"code":{"0":"C2"}}""",
                        "assign_queue": "send_project_to_queue",
                        "request_type": None,
                        
                    },
                )
            ],
            1,
        ),
        # Case 10: Multiple projects, one processed, one not
        (
            "multiple_projects_mixed",
            pd.concat(
                [
                    create_project_candidate_df("P1", PARSED_TIME),
                    create_project_candidate_df(
                        "P2", PARSED_TIME
                    ),  # Same time for simplicity
                ],
                ignore_index=True,
            ),
            [{"search_id": "S1", "territory_id": None}],
            SEARCH_MATERIALS_DF,
            {("P1", "S1", None, PARSED_TIME)},  # P1 processed
            set(),
            [  # Expect call only for P2
                call(
                    url=WORKFLOW_URL,
                    payload={
                        "project_id": "P2",
                        "time_created": EXPECTED_TIME,
                        "search_id": "S1",
                        "territory_id": [
                            {"territory_id": None, "distance_from_territory": None}
                        ],
                        "distance_from_territory": None,
                        "territory_idx": None,
                        "search_materials_json": """{"search_id":{"0":"S1"},"name":{"0":"S1"},"division":{"0":"D1"},"material":{"0":"M1"},"code":{"0":"C1"}}""",
                        "assign_queue": "send_project_to_queue",
                        "request_type": None,
                    },
                )
            ],
            1,
        ),
        # Case 11: Multiple projects, none processed
        ("multiple_projects_none_processed",
            pd.concat(
                [create_project_candidate_df("P"+str(x), PARSED_TIME) for x in range(20)], # create 20 projects
                ignore_index=True,
            ),
            [{"search_id": "S1", "territory_id": None}],
            SEARCH_MATERIALS_DF,
            {},  # No processed projects
            set(),
            [
                call(
                    url=WORKFLOW_URL,
                    payload={
                        "project_id": "P" + str(x),
                        "time_created": EXPECTED_TIME,
                        "search_id": "S1",
                        "territory_id": [
                            {"territory_id": None, "distance_from_territory": None}
                        ],
                        "distance_from_territory": None,
                        "territory_idx": None,
                        "search_materials_json":  """{"search_id":{"0":"S1"},"name":{"0":"S1"},"division":{"0":"D1"},"material":{"0":"M1"},"code":{"0":"C1"}}""",
                        "assign_queue": "send_project_to_queue",
                        "request_type": None,
                    },
                ) for x in range(20)
            ], # Expect 20 calls for 20 projects
            20, # Expect project_search_cnt to be 20
        ),
    ],
)

@patch("send_relevent_project_to_queue.get_processed_projects")
@patch("send_relevent_project_to_queue.get_non_related_project_searches")
@patch("send_relevent_project_to_queue.log_default")  # Mock logging to avoid noise
def test_project_search_to_task_queue_logic(
    mock_log,
    mock_get_non_related,
    mock_get_processed,
    test_id,
    project_candidates_df,
    search_id_ls,
    search_materials_df,
    processed_projects,
    non_related_searches,
    expected_calls,
    expected_project_search_cnt,
    mock_task_client,  # Fixture injection
    mock_bq_client,  # Fixture injection
    mock_settings,  # Fixture injection
):
    """Tests the core logic of project_search_to_task_queue."""
    print(f"\nRunning test case: {test_id}")  # Add print statement for clarity

    # Configure mocks
    mock_get_processed.return_value = processed_projects
    mock_get_non_related.return_value = non_related_searches

    # Call the function under test
    returned_count = project_search_to_task_queue(
        project_candidates_ls=project_candidates_df,
        search_id_ls=search_id_ls,
        search_materials_df=search_materials_df,
        task_client=mock_task_client,
        WORKFLOW_INVOCATION_URL=WORKFLOW_URL,
        bq_client=mock_bq_client,  # Pass mock bq_client
        settings=mock_settings,  # Pass mock settings
        FILE_PATH=TEST_FILE_PATH,
        TIME_CREATED=RAW_TIME_STR,
    )

    # Assertions
    if not expected_calls:
        mock_task_client.create_task.assert_not_called()
        print("Assertion: create_task not called (expected)")
    else:
        # Check if the calls were made, order doesn't matter for this logic
        mock_task_client.create_task.assert_has_calls(expected_calls, any_order=True)
        # Check the number of calls matches exactly
        assert mock_task_client.create_task.call_count == len(expected_calls)
        print(f"Assertion: create_task called {len(expected_calls)} times (expected)")
        print(f"Calls made: {mock_task_client.create_task.call_args_list}")
    
    # Check the returned count matches the expected count
    assert returned_count == expected_project_search_cnt
    print(f"Assertion: returned project_search_count: {returned_count} (expected)") 

# --- Keep the original integration test structure if needed, but adapt it ---
# You might want to keep a higher-level test that mocks less,
# or remove it if the specific unit tests above are sufficient.


# Example of adapting the original test structure (optional)
@patch("send_relevent_project_to_queue.invoke_cloud_function")
@patch("send_relevent_project_to_queue.GCPCloudTaskClient")
@patch("send_relevent_project_to_queue.BigQueryManager")
@patch("send_relevent_project_to_queue.get_settings")
def test_send_projects_to_queue_integration(
    mock_get_settings, mock_bq_manager, mock_task_client_class, mock_cloud_function, mock_settings
):
    """Higher-level integration test for the cloud function endpoint."""

    # --- Mock Setup ---
    # Use the injected mock_settings fixture directly
    mock_get_settings.return_value = mock_settings

    mock_bq_instance = Mock(spec=BigQueryManager)
    mock_bq_manager.return_value = mock_bq_instance

    mock_task_instance = Mock(spec=GCPCloudTaskClient)
    mock_task_client_class.return_value = mock_task_instance

    # Mock data returned by BigQueryManager
    # Example: Return an empty DataFrame for project candidates initially
    # Adjust these return values based on what you want the integration test to cover
    mock_bq_instance.query_table.side_effect = [
        pd.DataFrame(
            {  # project_candidates_query result
                "ProjectID": ["P1"],
                "sourceFileCreationTime": [datetime.fromisoformat(RAW_TIME_STR)],
                "Longitude": [-75.0],
                "Latitude": [40.0],
            }
        ),
        pd.DataFrame(
            {  # territories_query result
                "territory_id": ["T1"],
                "lat": [40.1],
                "lon": [-75.1],
            }
        ),
        [{"search_id": "S1", "territory_id": "T1"}],  # searches_query result
        pd.DataFrame({ 
            "search_id": ["S1"],
            "name": ["S1"], 
            "division": ["D1"],
            "material": ["M1"],
            "code": ["C1"],
        }), # search_materials_query result
        set(),  # get_processed_projects result
        set(),  # get_non_related_project_searches result
    ]

    # Mock HTTP request object
    mock_request = Mock()
    mock_data_dict = {
        "event": {
            "name": TEST_FILE_PATH,
            "timeCreated": RAW_TIME_STR,
        }
    }
    mock_request.get_json = lambda silent=True: mock_data_dict

    # --- Call the Cloud Function ---
    response = send_projects_to_queue(mock_request)

    # --- Assertions ---
    print("\nCloud Function Response (Integration Test):")
    print(json.dumps(response, indent=2))

    assert response["status"] == "success"
    assert response["log_message"] == "send_projects_to_queue completed successfully"

    # Check that BQ queries were called (adjust expected counts if needed)
    assert (
        mock_bq_instance.query_table.call_count >= 3
    )  # Project Candidates, Territories, Searches + potentially processed/non-related

    # Check that task client was initialized and create_task was called
    mock_task_client_class.assert_called_once_with(
        project=mock_settings.PROJECT_ID,
        location=mock_settings.CLOUD_TASK_LOCATION,
        queue=mock_settings.CLOUD_TASK_SEND_PROJECT_TO_QUEUE_QUEUE,
        service_account_email=mock_settings.WORKFLOW_INVOCATION_SA,
    )
    # Check if create_task was called (the exact payload depends on the mocked BQ results and find_nearby_branch logic)
    # In this specific setup, P1 is near T1, search S1 requires T1, nothing processed/non-related -> should call create_task
    mock_task_instance.create_task.assert_called()
    # You could add more specific assertions on the create_task payload if necessary


# --- Main execution block (for running tests directly) ---
if __name__ == "__main__":
    # Set environment variables if needed for local execution outside pytest
    # os.environ["DEPLOYMENT"] = "dev"
    # Note: Pytest handles fixtures and execution better.
    # Running specific tests: pytest test_send_project_to_queue.py -k test_project_search_to_task_queue_logic
    print("Running tests using pytest is recommended.")
    print("Example: pytest test_send_project_to_queue.py")
