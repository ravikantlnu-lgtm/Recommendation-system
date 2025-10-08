import unittest
from unittest.mock import MagicMock, Mock, patch
import pandas as pd
import numpy as np
import os
import sys 
from google.cloud.logging import Client
from google.cloud.logging.handlers import CloudLoggingHandler

# Get the directory of the current script
current_dir = os.path.dirname(os.path.abspath(__file__))

# Move one level up to the parent directory
parent_dir = os.path.abspath(os.path.join(current_dir, os.pardir))

# Add the parent directory to sys.path
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Import the Cloud Function and the specific function to test
from send_relevent_project_to_queue import (
    project_search_to_task_queue, 
    send_projects_to_queue,
)

from services import (  # Assuming GCPCloudTaskClient is in services
    BigQueryManager,
    GCPCloudTaskClient,
)

from logging_config import log_default

from config import get_settings

settings = get_settings()

"""
Query for finding project which is not related to search: 

SELECT s.project_id, s.search_id, m.sourcefile, m.sourceFileCreationTime, s.is_related
FROM `proj-sales-recommender-dev.sales_recommender_dev.assigned_search`  s 
    left join `proj-sales-recommender-dev.sales_recommender_dev.construct_connect_feed` m 
        on s.project_id = m.ProjectID WHERE s.is_related = "NO" and m.sourceFile is not null and m.sourceFileCreationTime is not null 
order by m.sourceFileCreationTime desc LIMIT 1

Returns: 
project_id
search_id
sourcefile
sourceFileCreationTime
is_related

1007553245
5ee2ab20-266c-4fc2-bac9-f784353df5a6
Delta/1.4_DL_FBMSales_XML_20250425.xml
2025-04-25T06:42:02.524Z
NO

---- 


Query for finding project which is already in relevance table:

select c.ProjectID, c.sourceFile, c.sourceFileCreationTime, r.search_id, r.territory_id, s.is_related, r.relevance 
from  `proj-sales-recommender-dev.sales_recommender_dev.construct_connect_feed` c 
    left join `proj-sales-recommender-dev.sales_recommender_dev.assigned_search` s
        on c.ProjectID = s.project_id 
    left join `proj-sales-recommender-dev.sales_recommender_dev.project_relevance` r 
        on s.search_id = r.search_id and s.territory_id LIKE CONCAT('%', r.territory_id, '%') 
where s.is_related = "YES" and c.sourceFile is not null and c.sourceFileCreationTime is not null 
order by c.sourceFileCreationTime desc limit 5

Returns 

ProjectID
sourceFile
sourceFileCreationTime
search_id
territory_id
is_related
relevance

1007594177
Delta/1.4_DL_FBMSales_XML_20250425.xml
2025-04-25T06:42:02.524Z
dd84e5a5-5d11-f011-9988-000d3a5a18fb
2c4bd3ba-60f5-ed11-8848-00224808db35
YES
High

"""
@patch("send_relevent_project_to_queue.process_project_without_territory")
@patch("send_relevent_project_to_queue.process_project_with_territories")
@patch("send_relevent_project_to_queue.GCPCloudTaskClient")
def test_project_assigned_branches_is_nan(
    project_candidates_ls, 
    search_id_ls,
    FILE_PATH, 
    TIME_CREATED, 
    mock_task_client_class,
    mock_process_with_territories,
    mock_process_without_territory,
):
    
    from logging_config import default_logger

    mock_task_client = Mock()
    mock_task_client_class.return_value = mock_task_client

    WORKFLOW_INVOCATION_URL = f"https://workflowexecutions.googleapis.com/v1/projects/{settings.PROJECT_ID}/locations/{settings.WORKFLOW_INVOCATION_LOCATION}/workflows/{settings.WORKFLOW_INVOCATION_NAME}/executions"
    
    task_client = GCPCloudTaskClient(
        project=settings.PROJECT_ID,
        location=settings.CLOUD_TASK_LOCATION,
        queue=settings.CLOUD_TASK_SEND_PROJECT_TO_QUEUE_QUEUE,
        service_account_email=settings.WORKFLOW_INVOCATION_SA,
    )

    bq_client = BigQueryManager(settings.BIGQUERY_DATASET)

    print("project_candidates_ls: ", project_candidates_ls)
    print("search_id_ls: ", search_id_ls)
    
    # Call the function
    project_search_to_task_queue(
        project_candidates_ls,
        search_id_ls,
        task_client,
        WORKFLOW_INVOCATION_URL,
        bq_client,
        settings,
        FILE_PATH,
        TIME_CREATED
    )

    # Assert that the process_project with/without_territory functions were not called
    mock_process_without_territory.assert_not_called() 
    mock_process_with_territories.assert_not_called()

    #  Assert that the task client did not create any tasks
    mock_task_client.create_task.assert_not_called()

    # Close the Cloud Logging client to clean up threads
    for handler in default_logger.handlers:
        if isinstance(handler, CloudLoggingHandler):
            handler.transport.worker.stop()  # Stop the background worker thread
    
if __name__ == "__main__":
    
    print("TEST 1: ")
    print("Testing when assigned_branches is NaN and project is not related to search")

    # Create inputs
    project_candidates_ls = pd.DataFrame(
        [
            {
                "ProjectID": 1007598633,
                "sourceFileCreationTime": "2025-04-25T06:42:02.524Z",
                "assigned_branches": np.nan,
            }
        ]
    )

    FILE_PATH = "Delta/1.4_DL_FBMSales_XML_20250425.xml"
    TIME_CREATED = "2025-04-25T06:42:02.524Z"
    search_id_ls = [{"search_id": "5ee2ab20-266c-4fc2-bac9-f784353df5a6", "territory_id": None}]

    test_project_assigned_branches_is_nan(
        project_candidates_ls,
        search_id_ls,
        FILE_PATH,
        TIME_CREATED,
    )
    print("test 1 passed.")

    print("TEST 2: ")
    print("Testing when assigned_branches is not null and project is not related to search")
    project_candidates_ls = pd.DataFrame(
            [
                {
                    "ProjectID": 1007598633,
                    "sourceFileCreationTime": "2025-04-25T06:42:02.524Z",
                    "assigned_branches":[{"territory_id": "9498e08c-2314-ee11-8f6e-00224808db35"}]
                }
            ]
        )
    
    test_project_assigned_branches_is_nan(
        project_candidates_ls,
        search_id_ls,
        FILE_PATH,
        TIME_CREATED,
    )
    print("test 2 passed.")

    print("TEST 3: ")
    print("Testing when assigned_branches is not null and project is already in relevance table")

    FILE_PATH = "Delta/1.4_DL_FBMSales_XML_20250425.xml"
    TIME_CREATED = "2025-04-25T06:42:02.524Z"
    search_id_ls = [{"search_id": "dd84e5a5-5d11-f011-9988-000d3a5a18fb", "territory_id": None}]

    project_candidates_ls = pd.DataFrame(
        [
            {
                "ProjectID": 1007594177,
                "sourceFileCreationTime": "2025-04-25T06:42:02.524Z",
                "assigned_branches": [{'territory_id': '2c4bd3ba-60f5-ed11-8848-00224808db35'}]
            }
        ]
    )

    test_project_assigned_branches_is_nan(
        project_candidates_ls,
        search_id_ls,
        FILE_PATH,
        TIME_CREATED,
    )

    print("test 3 passed.")
