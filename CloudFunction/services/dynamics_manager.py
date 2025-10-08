import json
from functools import lru_cache

import msal
import requests
import uuid
import functools

class RetryUtils:
    @staticmethod
    def retry_on_exception(max_retries=3, delay=0):
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):  # <- accepts any arguments, including 'self'
                last_exception = None
                for attempt in range(1, max_retries + 1):
                    try:
                        return func(*args, **kwargs)
                    except Exception as e:
                        print(f" DynamicsManager API call: Attempt {attempt} failed: {e}")
                        last_exception = e
                        if delay:
                            import time
                            time.sleep(delay)
                raise last_exception
            return wrapper
        return decorator

@lru_cache
class DynamicsManager:
    api_path = "api/data/v9.2"

    def __init__(self, domain, client_id=None, client_secret=None, access_token=None):
        self.domain = domain.strip("/")
        self.scopes = [f"{domain}/user_impersonation"]
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token  # Store access token directly

        self.headers = {
            "Accept": "application/json, */*",
            "content-type": "application/json; charset=utf-8",
        }
        if access_token:
            self.set_access_token(access_token)

    def set_access_token(self, token):
        """Sets the Token for its use."""
        assert token is not None, "The token cannot be None."
        self.access_token = token
        self.headers["Authorization"] = "Bearer " + self.access_token

    @RetryUtils.retry_on_exception(max_retries=3, delay=1)
    def build_msal_client(self, tenant_id):
        return msal.ConfidentialClientApplication(
            self.client_id,
            client_credential=self.client_secret,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
        )

    def get(self, endpoint, params=None, filter_by=None, select_fields=None, paginate=False):
        """Performs a GET request."""
        assert self.domain is not None, "'domain' is required"
        assert (
            self.access_token is not None
        ), "You must provide a 'token' to make requests"
        url = f"{self.domain}/{self.api_path}/{endpoint}"
        query_params = params.copy() if params else {}

        if filter_by:
            if isinstance(filter_by, dict):
                filter_clauses = []
                for col, val in filter_by.items():
                    if val is None or val == "None":
                        # Handle None values correctly for Dynamics OData
                        filter_clauses.append(f"{col} eq null")
                    else:
                        filter_clauses.append(f"{col} eq '{val}'")
                query_params["$filter"] = " and ".join(filter_clauses)
            else:
                raise ValueError("'filter_by' must be a dictionary or None.")
        if select_fields:
            if isinstance(select_fields, list):
                query_params["$select"] = ",".join(select_fields)
            else:
                raise ValueError("'select_fields' must be a list of field names.")

        try:
            response = requests.get(
                url, headers=self.headers, params=query_params, timeout=(10, 60)
            )
            response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
            data = response.json()

            if not paginate:
                return data

            return self._fetch_all_pages(data)
        except requests.exceptions.RequestException as e:
            if "response" in locals() and response is not None:
                raise requests.exceptions.RequestException(
                    f"GET Request Error: {e}\n"
                    f"Response status code: {response.status_code}\n"
                    f"Response body: {response.text if response.content else 'No content'}"
                )
            raise requests.exceptions.RequestException(f"GET Request Error: {e}\n")

    def post(self, endpoint, data=None):
        """Performs a POST request."""
        assert self.domain is not None, "'domain' is required"
        assert (
            self.access_token is not None
        ), "You must provide a 'token' to make requests"
        url = f"{self.domain}/{self.api_path}/{endpoint}"
        try:
            response = requests.post(url, headers=self.headers, json=data)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            if "response" in locals() and response is not None:
                raise requests.exceptions.RequestException(
                    f"POST Request Error: {e}\n"
                    f"Response status code: {response.status_code}\n"
                    f"Response body: {response.text if response.content else 'No content'}"
                )
            raise requests.exceptions.RequestException(f"POST Request Error: {e}\n")

    def patch(self, endpoint, filter_by, primary_attribute, data=None):
        """Performs a PATCH request."""
        assert self.domain is not None, "'domain' is required"
        assert (
            self.access_token is not None
        ), "You must provide a 'token' to make requests"
        assert (
            filter_by is not None and isinstance(filter_by, dict) and filter_by
        ), "'filter_by' is required and must be a non-empty dictionary"
        assert primary_attribute is not None, "'primary_attribute' is required"

        records = self.get(endpoint, filter_by=filter_by)
        if not records or "value" not in records:
            print("No matching records found.")
            return None

        for record in records["value"]:
            record_id = record[primary_attribute]
            url = f"{self.domain}/{self.api_path}/{endpoint}({record_id})"
            try:
                response = requests.patch(url, headers=self.headers, json=data)
                response.raise_for_status()
                if response.status_code not in [204, 200]:
                    raise Exception(f"Failed to update data into CRM: {response}")
            except requests.exceptions.RequestException as e:
                if "response" in locals() and response is not None:
                    raise requests.exceptions.RequestException(
                        f"PATCH Request Error: {e}\n"
                        f"Response status code: {response.status_code}\n"
                        f"Response body: {response.text if response.content else 'No content'}"
                    )
                raise requests.exceptions.RequestException(f"PATCH Request Error: {e}\n")
        return response

    @RetryUtils.retry_on_exception(max_retries=3, delay=1)
    def create_data(self, type=None, **kwargs):
        """Creates a new record."""
        if type is not None and kwargs is not None:
            return self.post(type, data=kwargs)
        raise ValueError("A type and data are necessary.")

    @RetryUtils.retry_on_exception(max_retries=3, delay=1)
    def get_data(self, type=None, params=None, filter_by=None, select_fields=None, paginate=False):
        """Retrieves records."""
        if type is not None:
            return self.get(
                type, params=params, 
                filter_by=filter_by, 
                select_fields=select_fields,
                paginate=paginate
            )
        raise ValueError("A type is necessary.")

    @RetryUtils.retry_on_exception(max_retries=3, delay=1)
    def update_data(
        self, update_values: dict, primary_attribute, type=None, filter_by=None
    ):
        """Updates a record."""
        if type is not None and primary_attribute is not None and filter_by is not None:
            return self.patch(
                type,
                filter_by=filter_by,
                primary_attribute=primary_attribute,
                data=update_values,
            )
        raise ValueError("A type, id and data are necessary.")
    
    def _build_batch_body(self ,records, entity_name, method="POST", primary_key=None):
        batch_id = f"batch_{uuid.uuid4()}"
        changeset_id = f"changeset_{uuid.uuid4()}"
        lines = []

        # Start of batch and changeset
        lines.append(f"--{batch_id}")
        lines.append(f"Content-Type: multipart/mixed;boundary={changeset_id}")
        lines.append("")

        for i, record in enumerate(records):
            lines.append(f"--{changeset_id}")
            lines.append("Content-Type: application/http")
            lines.append("Content-Transfer-Encoding: binary")
            lines.append(f"Content-ID: {i+1}")
            lines.append("")

            if method == "POST":
                url_line = f"POST {self.domain}/api/data/v9.2/{entity_name} HTTP/1.1"
                body = record
            elif method == "PATCH":
                if not primary_key or primary_key not in record:
                    raise ValueError(f"Missing primary key '{primary_key}' in record: {record}")
                entity_id = record[primary_key]
                url_line = f"PATCH {self.domain}/api/data/v9.2/{entity_name}({entity_id}) HTTP/1.1"
                body = record.copy()
                del body[primary_key]
            else:
                raise ValueError("Unsupported method. Only 'POST' and 'PATCH' are allowed.")

            lines.append(url_line)
            lines.append("Content-Type: application/json;type=entry")
            lines.append("")
            lines.append(json.dumps(body))

        # Close changeset and batch
        lines.append(f"--{changeset_id}--")
        lines.append(f"--{batch_id}--")
        lines.append("")

        return batch_id, "\r\n".join(lines)
    
    @RetryUtils.retry_on_exception(max_retries=3, delay=1)
    def send_batch_create(self,records, entity_name):
        """
        Sends a batch request to create multiple records in Dynamics CRM.
        """
        batch_id, batch_body = self._build_batch_body(records, entity_name, method="POST")

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": f"multipart/mixed;boundary={batch_id}",
            "Accept": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
        }
        try:
            url = f"{self.domain}/api/data/v9.2/$batch"
            response = requests.post(url, data=batch_body.encode("utf-8"), headers=headers)
            
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            if "response" in locals() and response is not None:
                raise requests.exceptions.RequestException(
                    f"POST Request Error: {e}\n"
                    f"Response status code: {response.status_code}\n"
                    f"Response body: {response.text if response.content else 'No content'}"
                )
            raise requests.exceptions.RequestException(f"POST Request Error: {e}\n")
        except Exception as e:
            raise Exception(f"An error occurred: {e}")

    @RetryUtils.retry_on_exception(max_retries=3, delay=1)
    def send_batch_update(self, records, entity_name, primary_key):
        """
        Sends a batch request to update multiple records in Dynamics CRM.
        """
        batch_id, batch_body = self._build_batch_body(records, entity_name, method="PATCH", primary_key=primary_key)

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": f"multipart/mixed;boundary={batch_id}",
            "Accept": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
        }
        try:
            url = f"{self.domain}/api/data/v9.2/$batch"
            response = requests.post(url, data=batch_body.encode("utf-8"), headers=headers)

            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            if "response" in locals() and response is not None:
                raise requests.exceptions.RequestException(
                    f"POST Request Error: {e}\n"
                    f"Response status code: {response.status_code}\n"
                    f"Response body: {response.text if response.content else 'No content'}"
                )
            raise requests.exceptions.RequestException(f"POST Request Error: {e}\n")
        except Exception as e:
            raise Exception(f"An error occurred: {e}")
        
    def _fetch_all_pages(self, initial_data, verbose=True):
        """Helper method to fetch all pages from a paginated OData response."""
        all_records = initial_data.get("value", [])
        next_link = initial_data.get("@odata.nextLink")
        page_count = 1

        while next_link:
            try:
                response = requests.get(next_link, headers=self.headers)
                response.raise_for_status()
                next_data = response.json()
                page_count += 1

                if verbose:
                    print(f"Page {page_count} -> record count = {len(next_data.get('value', []))}")

                all_records.extend(next_data.get("value", []))
                next_link = next_data.get("@odata.nextLink")
            except requests.exceptions.RequestException as e:
                print(f"Pagination error: {e}")
                break

        return {"value": all_records}
