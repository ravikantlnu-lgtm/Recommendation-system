import os 
import sys 
import argparse
import json
import requests 
from google.oauth2 import service_account
from google.auth.transport.requests import Request

# Add CloudFunction directory path (adjust if necessary)
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cloud_function_path = os.path.join(project_root, "CloudFunction")
if cloud_function_path not in sys.path:
    sys.path.insert(0, cloud_function_path)

os.chdir(cloud_function_path)
from config import get_settings
from utils.common import get_secret


def main(payload, url):    
    try:
        # Send HTTP POST request to the Cloud Function Workflow URL
        service_account_info = json.loads(get_secret(project_number=settings.PROJECT_ID, 
                                                 secret_name="default-service-account"))
        credentials = service_account.IDTokenCredentials.from_service_account_info(
            service_account_info,
            target_audience=url
        )
        # Refresh the credentials to get the identity token
        credentials.refresh(Request())
        token = credentials.token

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        response = requests.post(url, headers=headers, json=payload)

        # Print response
        print("\nCloud Function Workflow Response:")
        print(json.dumps(response.json(), indent=2))
    
    except requests.exceptions.RequestException as e:
        print(f"An error occurred while calling the Cloud Function Workflow: {e}")
        raise

if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Trigger the backfill_projects cloud function."
    )

    parser.add_argument(
        "--backfill_days",
        type=int,
        required=True,
        help="Number of days to backfill projects for.",
    )

    parser.add_argument(
        "--search_ids",
        type=str,
        default="",
        required=False,
        help="Comma-separated list of search uuids to process. If not provided, all searches will be processed.",
    )

    parser.add_argument(
        "--force_process",
        action="store_true",
        help="Force process projects even if they have been processed before.",
    )

    args = parser.parse_args()

    settings = get_settings()
    cloud_function_url = settings.BACKFILL_PROJECTS_CLOUD_FUNCTION_URL

    payload = { 
        "event": { 
            "backfill_days": args.backfill_days,
            "search_ids": args.search_ids,
            "force_process": args.force_process,
        }
    }

    print(f"Payload: {payload}")
    
    main(payload, url = cloud_function_url)
