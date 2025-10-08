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

# Import the Cloud Function directly
from backfill_projects import backfill_projects
from config import get_settings
from services import BigQueryManager

settings = get_settings()
big_query_client = BigQueryManager(dataset_id=settings.BIGQUERY_DATASET)


def test_backfill_projects(mock_data_dict):
    """Test the classify_project_cloud_function endpoint locally"""

    # Mock HTTP request object
    mock_request = Mock()
    mock_request.get_json = lambda silent=True: mock_data_dict

    try:
        # Call the cloud function
        response = backfill_projects(mock_request)

        # Print response
        print("\nCloud Function Response:")
        print(json.dumps(response, indent=2))

        # Assertions
        assert isinstance(response, dict)
        assert response["status"] == "success"
        assert response["log_message"] == "backfill_projects completed successfully"

    except AssertionError as e:
        print(f"Assertion failed: {e}")
        raise
    except Exception as e:
        print(f"An unexpected error occurred during the test: {e}")
        raise


if __name__ == "__main__":
    # Set environment variables for local testing
    import os

    start_time = datetime.now()

    print(f"start_time == {start_time}")
    os.environ["DEPLOYMENT"] = "dev"

    print("Starting local test of backfill_projects.py...")

    mock_data_dict = {
        "event": {
            "backfill_days": 2,
            "force_process": True,
            "search_ids": "0b3ab0d4-ec9-4ad2-974e-997e3055b839,5ee2ab20-266c-4fc2-bac9-f784353df5a6"
        }
    }

    test_backfill_projects(mock_data_dict)
    end_time = datetime.now()
    print(f"end_time == {end_time}")
    print(f"Execution time : {end_time-start_time}")
