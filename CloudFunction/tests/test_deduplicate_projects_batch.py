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
from deduplicate_projects_batch import deduplicate_projects_batch
from services import BigQueryManager, FirestoreClass  # Added FirestoreClass

settings = get_settings()
big_query_client = BigQueryManager(dataset_id=settings.BIGQUERY_DATASET)


def test_deduplicate_projects_batch(mock_data_dict):
    """Test the classify_project_cloud_function endpoint locally"""

    # Mock HTTP request object
    mock_request = Mock()
    mock_request.get_json = lambda silent=True: mock_data_dict

    try:
        # Call the cloud function
        response = deduplicate_projects_batch(mock_request)

        # Print response
        print("\nCloud Function Response:")
        print(json.dumps(response, indent=2))

        # Assertions
        assert isinstance(response, dict)
        assert response["status"] == "success"
        assert (
            response["log_message"] == "deduplicate_projects_batch completed successfully."
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

    print("Starting local test of deduplicate_projects_batch.py...")

    try:
        # Prepare mock data
        mock_data_dict = {
            "event": {
                "name": "Delta/Unified_20250605.xml",
                "timeCreated": "2025-06-05T14:10:15",
                "bucket": "dodge_full_dump",
                "batch_id": "3d961cd0-c9f8-4619-aa4e-fd81d8e2db0f"
            }
        }

        # 5. Run the test
        test_deduplicate_projects_batch(mock_data_dict)

    except Exception as e:
        print(f"An error occurred during test setup or execution: {e}") 

