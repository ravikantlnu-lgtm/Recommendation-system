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


from batch_upsert_leads import batch_upsert_leads
from services import BigQueryManager

settings = get_settings()
big_query_client = BigQueryManager(dataset_id=settings.BIGQUERY_DATASET)


def test_batch_upsert_leads(mock_data_dict):
    """Test the process_xml endpoint locally"""

    # Mock HTTP request object
    mock_request = Mock()
    mock_request.get_json = lambda silent=True: mock_data_dict

    try:
        # Call the cloud function
        response = batch_upsert_leads(mock_request)

        # Print response
        print("\nCloud Function Response:")
        print(json.dumps(response, indent=2))

        # Assertions
        assert isinstance(response, dict)
        assert response["status"] == "success"
        assert response["log_message"] in [
            "Successfully upserted leads into CRM."
        ]

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


    print("Starting local test of batch_upsert_leads.py...")

    mock_data_dict = {
        "event": {
            "name": "Delta/1.4_DL_FBMSales_XML_20250718.xml",
            "timeCreated": "2025-07-18T06:35:54",
            "batch_id": 'a423bde0-a5f2-438b-8001-5f4f82607763'
            # "backfill": True,
            # "search_ids" : "16700387-5d11-f011-9988-000d3a5a18fb,70e6309f-5d11-f011-9988-000d3a5a18fb"

        }
    }
   
    test_batch_upsert_leads(mock_data_dict)
