import json
import os
import sys
from unittest.mock import MagicMock, Mock, patch

import pytest
from google.cloud import secretmanager

# Get the directory of the current script
current_dir = os.path.dirname(os.path.abspath(__file__))

# Move one level up to the parent directory
parent_dir = os.path.abspath(os.path.join(current_dir, os.pardir))

# Add the parent directory to sys.path
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from config import get_settings
from search_territory_updates import search_territory_updates
from services import BigQueryManager

settings = get_settings()


def get_secret(secret_id, version_id="latest"):
    """Get secret from GCP Secret Manager"""
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{settings.PROJECT_ID}/secrets/{secret_id}/versions/{version_id}"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")


def test_search_territory_updates(mock_data_dict):
    """Test the classify_project_cloud_function endpoint locally"""

    # Mock HTTP request object
    mock_request = Mock()
    mock_request.get_json = lambda silent=True: mock_data_dict

    try:
        # Call the cloud function
        response = search_territory_updates(mock_request)

        # Print response
        print("\nCloud Function Response:")
        print(json.dumps(response, indent=2))

        # Assertions
        assert isinstance(response, dict)
        assert response["status"] == "success"
        assert response["log_message"] == "Tables synced successfully."

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

    print("Starting local test of send_project_to_queue.py...")

    mock_data_dict = {}

    test_search_territory_updates(mock_data_dict)
