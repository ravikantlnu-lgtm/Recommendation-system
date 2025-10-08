import os
from google.cloud import storage , bigquery
from io import BytesIO
from datetime import datetime
from google.auth.transport.requests import Request
from google.oauth2 import service_account
import json
import concurrent.futures
import time
import subprocess
from google.auth.transport.requests import Request
import requests
from google.oauth2 import service_account
import re
from logging_config import log_default, log_error
import traceback


def process_files_in_batches(big_query_client, settings, source_filepath,timeCreated,files,CLOUD_FUNCTION_URL, batch_size):

    error_files = {}
    
    num_rows = 0
    for i in range(0, len(files), batch_size):
        batch = files[i : i + batch_size]

        log_default(log_message=f"Processing batch {i // batch_size + 1} with {len(batch)} files...",
                    json_payload=json.dumps({"filename": source_filepath})
        )
        with concurrent.futures.ThreadPoolExecutor(max_workers=batch_size) as executor:
            future_to_file = {executor.submit(invoke_cloud_function_with_retry, source_filepath,timeCreated,CLOUD_FUNCTION_URL,file,settings.GCS_BUCKET): file for file in batch}
            
            for future in concurrent.futures.as_completed(future_to_file):
                file_name = future_to_file[future]
                try:
                    status_code , response_text = future.result()
                    match = re.search(r'num_rows<(\d+)>', response_text)
                    num_rows = num_rows + int(match.group(1)) if match else 0 
                    response_text = json.loads(response_text)

                    if response_text.get("status") != "success":
                        error = f"Error processing {file_name}: {response_text}"
                        raise Exception(error)

                    log_default(log_message=f"Processed {file_name}:{response_text}",
                                json_payload=json.dumps({"filename": source_filepath})
                    )
                except Exception as e:
                    
                    stack_trace = traceback.format_exc()
                    error_files[file_name] = stack_trace
                    log_error(
                        function_name="process_files_in_batches",
                        endpoint="split-large-xml-files",
                        log_message=f"Error processing {file_name}: {str(e)}",
                        error_type=type(e).__name__,
                        stack_trace=stack_trace,
                        json_payload=json.dumps({"filename": source_filepath,"time_created": timeCreated})
                    )

        if error_files:
            # Deleting the records from the table if any errors occur 
            query = f"""Delete from {settings.BIGQUERY_DATASET}.{settings.CC_FEED_TABLE_ID}
                    where sourceFile='{source_filepath}' """
            big_query_client.query_table(query=query)
            raise Exception(f"Error processing {error_files}")
        
        log_default(log_message=f"Batch {i // batch_size + 1} completed.",
                    json_payload=json.dumps({"filename": source_filepath})
        )
        time.sleep(2) 
    return num_rows
    
def invoke_cloud_function_with_retry(source_filepath, timeCreated, CLOUD_FUNCTION_URL, file_path, bucket, retries=3):
    for attempt in range(retries):
        status_code , response_text = invoke_cloud_function(source_filepath,timeCreated,CLOUD_FUNCTION_URL, file_path, bucket)
        if status_code == 200:
            return status_code , response_text
        log_default(log_message=f"Retrying {file_path}, attempt {attempt + 1}",
                    json_payload=json.dumps({"filename": source_filepath})
        )
        time.sleep(3) 
    raise f"Failed to process {file_path} after {retries} attempts.{response_text}"

def invoke_cloud_function(source_filepath,timeCreated,CLOUD_FUNCTION_URL, file_path, bucket):
    # Load service account credentials
    service_account_info = json.loads(os.getenv("default-service-account"))
    credentials = service_account.IDTokenCredentials.from_service_account_info(
        service_account_info,
        target_audience=CLOUD_FUNCTION_URL
    )

    # Refresh the credentials to get the identity token
    auth_request = Request()
    credentials.refresh(auth_request)
    token = credentials.token

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "event": 
            {
                "name": file_path, 
                "timeCreated": timeCreated, 
                "source_filepath": source_filepath, 
                "splitted": True, 
                "bucket":bucket
            }
        }

    try:
        response = requests.post(CLOUD_FUNCTION_URL, headers=headers, json=payload)
        return response.status_code, response.text
    except requests.RequestException as e:
        raise f"Error invoking cloud function: {e}"

    
def download_gcs_file(gcs_client, file_path):
    f_name = file_path.split('/')[-1]
    temp_filename = f'temp_file_{f_name}'
    gcs_client.download_by_filename(file_path, temp_filename)

    log_default(log_message=f"Downloaded {file_path} file...",
                json_payload=json.dumps({"filename": file_path})
    )
    return temp_filename

def split_large_xml(input_file, output_prefix, gcs_client, batch_size=100):
    """Splits an XML file based on <Project> elements while preserving the XML structure."""
    project_count = 0
    file_count = 1
    batch = []
    header = []
    footer = []
    in_project = False

    with open(input_file, "r", encoding="utf-8") as file:
        lines = file.readlines()  # Read all lines once to detect footer
        total_lines = len(lines)
        
        
        # Detect XML footer (last non-empty line)
        for i in range(total_lines - 1, -1, -1):
            if lines[i].strip():  # Ignore empty lines
                footer = [lines[i]]  # Store the last line as footer
                break
        
        splitted_file_ls = []
        for line in lines:
            if not in_project:
                if "<Project " in line:
                    in_project = True
                    batch.append(line)
                    project_count += 1
                else:
                    if not batch:
                        header.append(line)  # Only add to header if batch isn't started
            else:
                batch.append(line)
                if "</Project>" in line:
                    in_project = False

                    # If batch is full, write to a new file
                    if project_count >= batch_size:
                        blob_name = write_xml_file(header, batch, footer, output_prefix, file_count,gcs_client,input_file)
                        file_count += 1
                        batch = []
                        project_count = 0
                        splitted_file_ls.append(blob_name)

        # Write remaining projects
        if batch:
            blob_name = write_xml_file(header, batch, footer, output_prefix, file_count,gcs_client,input_file)
            splitted_file_ls.append(blob_name)
        
        return splitted_file_ls

def write_xml_file(header, batch, footer, output_prefix, file_count, gcs_client,input_file):
    """Helper function to write a batch of projects into a new XML file and upload to GCS."""

    file_name = f"tmp/{input_file}/{output_prefix}_{file_count}.xml"
    in_memory_file = BytesIO()

    # Write to in-memory file
    in_memory_file.write("".join(header).encode("utf-8"))
    in_memory_file.write("".join(batch).encode("utf-8"))
    in_memory_file.write("".join(footer).encode("utf-8"))
    in_memory_file.seek(0)  # Reset file pointer to the beginning

    blob=gcs_client.upload_file(file_name, in_memory_file, content_type = "application/xml")
   

    log_default(log_message=f"Saved {file_name} to GCS bucket {gcs_client._bucket}",
                json_payload=json.dumps({"filename": input_file})
    )
    return blob.name


def delete_folder(gcs_client, folder_name):
    gcs_client.delete_files_from_directory(folder_name)
   

def insert_log(dataset, table, file_path, rows, big_query_client):
    query = f"""Insert into {dataset}.{table} (file_path, num_rows, status) values ('{file_path}', {rows}, 'Success')"""
    query_job = big_query_client.query_table(query)
    log_default(log_message=f'Inserted log for {file_path}',
                json_payload=json.dumps({"filename": file_path})
    )
    return query_job.state
