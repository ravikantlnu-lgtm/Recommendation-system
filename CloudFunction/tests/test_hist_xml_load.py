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


from hist_xml_load import gcs_to_bq
from services import BigQueryManager

settings = get_settings()
big_query_client = BigQueryManager(dataset_id=settings.BIGQUERY_DATASET)


def test_gcs_to_bq(mock_data_dict):
    """Test the process_hist_xml endpoint locally"""

    # Mock HTTP request object
    mock_request = Mock()
    mock_request.get_json = lambda silent=True: mock_data_dict

    try:
        # Call the cloud function
        response = gcs_to_bq(mock_request)

        # Print response
        print("\nCloud Function Response:")
        print(json.dumps(response, indent=2))

        # Assertions
        assert isinstance(response, dict)
        assert response["status"] == "success"
        

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


    print("Testing construct_connect delta file.")
    mock_data_dict = {
        "event": {
            'name': 'Delta/1.4_DL_FBMSales_XML_20250609.xml', 
            'timeCreated': '2025-06-09T06:30:21.822000Z', 
            'bucket': 'construct_connect_full_dump'
        }
    }
    test_gcs_to_bq(mock_data_dict)

    print("Testing Dodge delta file...")
    mock_data_dict = {
        "event":{
            'name': 'Delta/Unified_20250606.xml', 
            'timeCreated': '2025-06-10T10:20:24.580000Z', 
            'bucket': 'dodge_full_dump'
        }
    }
    
    test_gcs_to_bq(mock_data_dict)