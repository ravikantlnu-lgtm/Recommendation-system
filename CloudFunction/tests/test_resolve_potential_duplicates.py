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
from resolve_potential_duplicates import resolve_potential_duplicates
from services import BigQueryManager, FirestoreClass  # Added FirestoreClass

settings = get_settings()
big_query_client = BigQueryManager(dataset_id=settings.BIGQUERY_DATASET)


def test_resolve_potential_duplicates(mock_data_dict):
    """Test the classify_project_cloud_function endpoint locally"""

    # Mock HTTP request object
    mock_request = Mock()
    mock_request.get_json = lambda silent=True: mock_data_dict

    try:
        # Call the cloud function
        response = resolve_potential_duplicates(mock_request)

        # Print response
        print("\nCloud Function Response:")
        print(json.dumps(response, indent=2))

        # Assertions
        assert isinstance(response, dict)
        assert response["status"] == "success"
        assert (
            response["log_message"] == "resolve_potential_duplicates completed successfully"
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

    print("Starting local test of resolve_potential_duplicates.py...")

    try:
        # Prepare mock data
        mock_data_dict = {
            
                "batch_id": "3d961cd0-c9f8-4619-aa4e-fd81d8e2db0f",
                "bucket": "dodge_full_dump",
                "distance": 0.2780796825619937,
                "name": "Delta/Unified_20250605.xml",
                "project_1": {
                "DRNumber": 202500079692,
                "FeaturesInfo": "Elevator Addition and Interior Alterations at the Glen Rock Public \nLibrary",
                "Lat": "40.9626800",
                "Long": "-74.1264300",
                "MarketSegment": "School",
                "OwnershipType": "Local Government",
                "PrimaryProjectType": "Library",
                "ProjectTitle": "Glen Rock Public Library Elevator Addition & Int Alter",
                "StatusText": "Bids to Owner July 08 at 10:00 AM (EDT) - Previous Bids of April 02 has Cancelled.",
                "TypeOfWork": "Interiors",
                "Valuation": "2000000",
                "owner_name": "Borough of Glen Rock",
                "source": "dodge"
                },
                "project_1_source": "dodge",
                "project_2": {
                "Details_Detail_Details": [
                    "[Division 2]: Building Demolition, Clearing, Dewatering, Shoring, Earthwork, Slope Protection & Erosion Control, Tunneling, Paving & Surfacing, Water Systems, Sewerage & Drainage, Landscaping. [Division 3]: Concrete Formwork, Concrete Reinforcement, Structural Concrete, Structural Precast Concrete, Concrete Restoration & Cleaning. [Division 4]: Clay Unit Masonry. [Division 5]: Cold Formed Metal Framing, Metal Fabrications, Metal Railings. [Division 6]: Rough Carpentry, Finish Carpentry, Architectural Woodwork. [Division 7]: Waterproofing, Insulation, Shingles, Manufactured Roofing & Siding, Skylights. [Division 8]: Metal Doors, Wood Doors, Entrances & Storefronts, Hardware, Glass & Glazing. [Division 9]: Ceiling Suspension Systems, Drywall/Gypsum, Tile, Acoustical Ceilings, Resilient Flooring, Carpet, Painting. [Division 10]: Louvers & Vents, Interior Signs. [Division 12]: Manufactured Casework. [Division 14]: Elevators. [Division 15]: Ductwork. [Division 16]: Service/Distribution. "
                ],
                "Details_Detail_Notes": [
                    "Development include(s):  Renovation\nBid Date: 07/08/2025 10:00AM Rebid update from 4/2/2025. All bids will be publicly opened at Borough Hall, Borough Hall Address is 1 Harding Plaza, Glen Rock, NJ 07452 and read . All Bids must be delivered, either by mail, express delivery service, or dropped off in exterior drop box, to the Office of the Borough Administrator.\nSite Walkthrough: 06/10/2025 10:00AM A pre-bid conference and walk through will be held at the Glen Rock Public Library. While not mandatory Bidders are encouraged to attend."
                ],
                "Details_Detail_Scope": [
                    "Renovation of a library in Glen Rock, New Jersey. Completed plans call for the renovation of a library.\nGlen Rock Public Library Elevator Addition and Interior Alterations. Each bidder shall deposit with its bid a certified check or cashiers check, or bid guarantee in the form of a bid bond (cash will not be accepted) drawn to Borough of Glen Rock, in the amount of ten percent (10%) but not to exceed $20,000 of the total bid, as provided in the said specifications, as a guarantee of good faith in bidding and shall also submit a certificate from a surety company stating that it will provide the bidder with a bond in such sum as is required in the advertisement or in the specifications. All questions or Requests for Information shall be emailed to the Architect as follows: Subject: Elevator Addition and Interior Alterations at the Glen Rock Public Library RFI - RSC Architects, Bidding@rscarchitects.com, 201-941-3040"
                ],
                "Latitude": 40.966029,
                "Longitude": -74.123474,
                "Parameters_Parameter_Ownership": "City",
                "Parameters_Parameter_WorkType": "Alteration",
                "ParentCategories_ParentCategory": [
                    {
                    "Name": "COMMUNITY",
                    "SubCategories": {
                        "SubCategory": [
                        "Libraries"
                        ]
                    }
                    }
                ],
                "ParentCategories_PrimaryCategoryName": "Libraries",
                "Title": "Elevator Addition and Interior Alterations at the Glen Rock Public Library",
                "Valuation_Value": "900000.00",
                "owner_name": "Borough of Glen Rock",
                "ProjectID": 1007519523,
                "source": "construct_connect"
                },
                "project_2_source": "construct_connect",
                "timeCreated": "2025-06-05T14:10:15"
        
        }

        # 5. Run the test
        test_resolve_potential_duplicates(mock_data_dict)

    except Exception as e:
        print(f"An error occurred during test setup or execution: {e}")

