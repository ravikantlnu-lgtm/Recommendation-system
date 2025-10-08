import json
import os
import sys
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

from config import get_settings

# Import the Cloud Function directly
from send_relevent_project_to_queue import send_projects_to_queue
from services import BigQueryManager, FirestoreClass  # Added FirestoreClass

settings = get_settings()
big_query_client = BigQueryManager(dataset_id=settings.BIGQUERY_DATASET)


def test_send_projects_to_queue(mock_data_dict):
    """Test the classify_project_cloud_function endpoint locally"""

    # Mock HTTP request object
    mock_request = Mock()
    mock_request.get_json = lambda silent=True: mock_data_dict

    try:
        # Call the cloud function
        response = send_projects_to_queue(mock_request)

        # Print response
        print("\nCloud Function Response:")
        print(json.dumps(response, indent=2))

        # Assertions
        assert isinstance(response, dict)
        assert response["status"] == "success"
        assert (
            response["log_message"] == "send_projects_to_queue completed successfully"
        )

    except AssertionError as e:
        print(f"Assertion failed: {e}")
        raise
    except Exception as e:
        print(f"An unexpected error occurred during the test: {e}")
        raise


if __name__ == "__main__":
    # Set environment variables for local testing
    import os

    os.environ["DEPLOYMENT"] = "dev"

    print("Starting local test of send_project_to_queue.py...")

    try:
        # Prepare mock data
        mock_data_dict = {
            "event": {
                "name": "Delta/1.4_DL_FBMSales_XML_20250423.xml",
                "timeCreated": "2025-04-23T06:41:35.174Z",
                "force_process": True,
                "bucket": "construct_connect_full_dump"
            }
        }

        # 5. Run the test
        test_send_projects_to_queue(mock_data_dict)

    except Exception as e:
        print(f"An error occurred during test setup or execution: {e}")

