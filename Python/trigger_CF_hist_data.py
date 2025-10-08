# parllel processing cloud fun
import google.auth
from google.auth.transport.requests import Request
from google.oauth2 import service_account
import requests
import subprocess
import json
from google.cloud import storage,bigquery
import concurrent.futures
import time

# Configurations
BUCKET_NAME = "construct_connect_full_dump"
HIST_LOAD_CLOUD_FUNCTION_URL = "https://process-hist-xml-files-195063057478.us-west1.run.app"
SPLIT_XML_CLOUD_FUNCTION_URL = "https://split-large-xml-files-195063057478.us-west1.run.app"
MAX_PARALLEL_CALLS = 80  # Number of functions to run in parallel
SOURCE_PROJECT_ID = 'looker-studio-pro-427717'
PROJECT_ID = "proj-sales-recommender-dev"
PREFIX = "History/cmd_leads_files_2"
LOG_TABLE = "proj-sales-recommender-dev.sales_recommender_dev.hist_construct_connect_feed_log"


def get_gcs_files(project, bucket_name, prefix):
    """Fetch list of files from GCS bucket and categorize them by size."""
    storage_client = storage.Client(project)
    bucket = storage_client.bucket(bucket_name)
    blobs = bucket.list_blobs(prefix=prefix)

    large_files = []
    small_files = []

    for blob in blobs:
        if blob.size > 1 * 1024 * 1024 * 1024:  # 1 GB in bytes
            large_files.append(blob.name)
        else:
            small_files.append(blob.name)

    return large_files,small_files



def invoke_cloud_function(file_path,CLOUD_FUNCTION_URL):

    # Added 'historical_file' in the payload to specify the type of file
    payload = json.dumps({"event": {"name": file_path ,"splitted":True ,"historical_file":True}})

    curl_command = f"""
    curl -X POST {CLOUD_FUNCTION_URL} \
    -H "Authorization: bearer $(gcloud auth print-identity-token)" \
    -H "Content-Type: application/json" \
    -d '{payload}'
    """

    try:
        result = subprocess.run(curl_command, shell=True, text=True, capture_output=True, check=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        return f"Error: {e.stderr}"
    

    
def process_files_in_batches(files, batch_size,CLOUD_FUNCTION_URL):

    for i in range(0, len(files), batch_size):
        batch = files[i : i + batch_size]

        print(f"Processing batch {i // batch_size + 1} with {len(batch)} files...")

        with concurrent.futures.ThreadPoolExecutor(max_workers=batch_size) as executor:
            future_to_file = {executor.submit(invoke_cloud_function, file,CLOUD_FUNCTION_URL): file for file in batch}
            
            for future in concurrent.futures.as_completed(future_to_file):
                file_name = future_to_file[future]
                try:
                    result = future.result()
                    print(f"Processed {file_name}:{result}")
                except Exception as e:
                    print(f"Error processing {file_name}: {e}")

        print(f"Batch {i // batch_size + 1} completed.\n")
        time.sleep(2)  

def get_processed_file_ls(project,LOG_TABLE):
    bq_client = bigquery.Client(project=project)
    query = f"select file_path from {LOG_TABLE}"
    result = bq_client.query(query=query)
    processed_file_ls = []
    for i in result.result():
        processed_file_ls.append(i[0])
    return processed_file_ls
# Example usage
if __name__ == "__main__":
    print("Fetching file details from GCS...")
    large_files, small_files = get_gcs_files(SOURCE_PROJECT_ID,BUCKET_NAME,PREFIX)
    processed_file_ls = get_processed_file_ls(PROJECT_ID,LOG_TABLE)


    small_files_ls = []
    large_files_ls = []


    for i in small_files:
        if i  in processed_file_ls:
            continue
        small_files_ls.append(i)
    
    for i in large_files:
        if i  in processed_file_ls:
            continue
        large_files_ls.append(i)
    
    if not small_files_ls:
        print("No small files found in the bucket.")
    else:
        print(f"Total files found: {len(small_files_ls)}")
        process_files_in_batches(small_files_ls, MAX_PARALLEL_CALLS,HIST_LOAD_CLOUD_FUNCTION_URL)
       

    if not large_files_ls:
        print("No Large files found in the bucket.")
    else:
        print(f"Total files found: {len(large_files_ls)}")

        for file in large_files_ls:
            print(f"Invoking cloud function for : {file}")
            invoke_cloud_function(file , SPLIT_XML_CLOUD_FUNCTION_URL)

    
    