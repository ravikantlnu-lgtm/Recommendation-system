import json
import os
import sys
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pandas as pd
import pytest
from functions_framework import create_app
from google.cloud import secretmanager

# Get the directory of the current script
current_dir = os.path.dirname(os.path.abspath(__file__))

# Move one level up to the parent directory
parent_dir = os.path.abspath(os.path.join(current_dir, os.pardir))

# Add the parent directory to sys.path
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from config import get_settings


from split_large_xml_files import split_xml
from services import BigQueryManager

settings = get_settings()
big_query_client = BigQueryManager(dataset_id=settings.BIGQUERY_DATASET)

def get_secret(secret_id, version_id="latest"):
    """Get secret from GCP Secret Manager"""
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{settings.PROJECT_ID}/secrets/{secret_id}/versions/{version_id}"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")



def test_split_xml(mock_data_dict):
    """Test the split_large_xml_files endpoint locally"""

    # Mock HTTP request object
    mock_request = Mock()
    mock_request.get_json = lambda silent=True: mock_data_dict

    try:
        # Call the cloud function
        response = split_xml(mock_request)

        # Print response
        print("\nCloud Function Response:")
        print(json.dumps(response, indent=2))

        # Assertions
        assert isinstance(response, dict)
        assert response["status"] == "success"
        assert (
            response["log_message"] == "Processed large XML file."
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

    default_service_account = get_secret("default-service-account")  # Replace with your secret name

    os.environ["default-service-account"] = default_service_account
    print("Starting local test of hist_xml_load.py...")

    

    mock_data_dict = {
        "event": {
            "name": "Delta/1.4_DL_FBMSales_XML_20241223.xml",
            "timeCreated": "2025-03-13T12:32:07.918361",
            "historical_file": False
        }
    }

    test_split_xml(mock_data_dict)
