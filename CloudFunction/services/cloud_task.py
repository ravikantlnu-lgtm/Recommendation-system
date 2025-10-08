from google.cloud import tasks_v2
from google.protobuf import timestamp_pb2
import base64
import json
import datetime
import time
import google.api_core.exceptions



def retry_with_exponential_backoff(max_retries=5, base_delay=2):
    """Decorator for retrying a function with exponential backoff."""

    def decorator(func):
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)  # Try the function
                except google.api_core.exceptions.ServiceUnavailable as e:
                    if attempt < max_retries - 1:
                        wait_time = base_delay * (2**attempt)  # Exponential backoff
                        print(
                            f"Retry {attempt + 1}/{max_retries} - Retrying in {wait_time} seconds..."
                        )
                        time.sleep(wait_time)
                    else:
                        print("Max retries reached. Raising exception.")
                        raise e  # Raise error after max retries

        return wrapper

    return decorator

class GCPCloudTaskClient:
    def __init__(
        self, project, location, queue, service_account_email, fail_once=False
    ):
        self.client = tasks_v2.CloudTasksClient()
        self.parent = self.client.queue_path(project, location, queue)
        self.service_account_email = service_account_email
        self.fail_once = fail_once  # Flag to force one failure

    @retry_with_exponential_backoff(max_retries=5, base_delay=2)
    def create_task(self, url, payload=None, in_seconds=None):
        if self.fail_once:
            self.fail_once = False  # Ensure it fails only once
            raise google.api_core.exceptions.ServiceUnavailable("Simulated failure")

        # Convert the payload to a JSON string
        if payload:
            payload = {"data": payload}
            payload = {"argument": json.dumps(payload)}

        task = {
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": url,
                "oauth_token": {"service_account_email": self.service_account_email},
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(payload).encode(),
            }
        }

        request = tasks_v2.CreateTaskRequest(parent=self.parent, task=task)

        if in_seconds is not None:
            d = datetime.datetime.utcnow() + datetime.timedelta(seconds=in_seconds)
            timestamp = timestamp_pb2.Timestamp()
            timestamp.FromDatetime(d)
            task["schedule_time"] = timestamp  # Use dictionary key assignment

        print("task", task)
        response = self.client.create_task(request=request)
        print("Created task {}".format(response.name))
        return response