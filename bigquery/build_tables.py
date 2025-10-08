import json
import os
from datetime import datetime
import time 
import subprocess

# import queries
from google.cloud import bigquery
import subprocess


# Determine which configuration to use
env = os.getenv("ENV", "dev")  # Default to 'dev' if ENV is not set

if env == "prod":
    import config_prod as config
else:
    import config_dev as config

current_path = os.path.dirname(os.path.abspath(__file__))
fh = open(f"{current_path}/tables_metadata_info.json", "r")
tables_metadata = json.loads(fh.read())
part_clus_dict = tables_metadata["partition_cluster_info"]
pk_fk_dict = tables_metadata["pk_fk_info"]
default_values_dict = tables_metadata["default_values_info"]

def run_bq_command_with_retry(command: str, max_retries: int = 5, initial_delay: int = 2):
    """
    Executes a BigQuery command using subprocess, with exponential backoff for rate limit errors.
    """
    retries = 0
    while retries < max_retries:
        try:
            # Using capture_output to check stderr for specific errors
            result = subprocess.run(f"bq query --use_legacy_sql=false '{command}'", shell=True, check=True, capture_output=True, text=True)
            # Command was successful
            return result
        except subprocess.CalledProcessError as e:
            # Only retry on specific, retryable errors like rate limits.
            if "rateLimitExceeded" in e.stderr:
                retries += 1
                if retries >= max_retries:
                    print(f"Max retries reached for command: {command}")
                    raise e  # Re-raise the exception after the last attempt
                
                # Calculate exponential backoff time
                delay = initial_delay * (2 ** (retries - 1))
                print(f"Rate limit exceeded. Retrying in {delay} seconds... (Attempt {retries}/{max_retries})")
                time.sleep(delay)
            else:
                # For all other errors (like invalid query), fail immediately.
                print(f"Command failed with a non-retryable error: {e.stderr}")
                raise e
            
            
def create_dataset_if_not_exists():
    # Initialize BigQuery client
    client = bigquery.Client()

    # Define the dataset ID
    dataset_id = f"{config.PROJECT_ID}.{config.BIGQUERY_DATASET}"

    # Check if the dataset exists
    try:
        client.get_dataset(dataset_id)  # Make an API request.
        print(f"Dataset {dataset_id} already exists.")
    except Exception:
        # Dataset does not exist, create it
        dataset = bigquery.Dataset(dataset_id)
        dataset.location = "US"  # Set the location as needed
        client.create_dataset(dataset)  # Make an API request.
        print(f"Created dataset {dataset_id}.")

def remove_constraint(bq_table_id, column_name): 
    """
    Removes primary or foreign key constraints for a given column in a BigQuery table. 
    Used to alter column types that are part of a constraint.
    """
    # Fetch primary key and foreign key constraints
    constraints = bq_table_id._properties.get("tableConstraints") if bq_table_id is not None else None 
    if not constraints:
        return

    # Remove primary key constraint for column 
    primary_constraints = constraints.get("primaryKey", {}) 
    if "columns" in primary_constraints and column_name in primary_constraints["columns"]:
        remove_pk_sql = f"ALTER TABLE `{bq_table_id}` DROP PRIMARY KEY" 
        print(remove_pk_sql)
        run_bq_command_with_retry(remove_pk_sql)
        return 
    
    # Remove foreign key constraints for column
    foreign_keys_lst = constraints.get("foreignKeys", []) 
    for foreign_key in foreign_keys_lst: 
        # Get constraint name 
        foreign_key_constraint_name = foreign_key.get("name", "") 
        column_reference = foreign_key.get("columnReferences", [])
        # Check if the column is referencing in the foreign key
        if column_reference and column_reference[0].get("referencingColumn") == column_name:
            remove_fk_sql = f"ALTER TABLE `{bq_table_id}` DROP CONSTRAINT {foreign_key_constraint_name}"
            print(remove_fk_sql)
            run_bq_command_with_retry(remove_fk_sql)
        
    return 

def update_column_type(bq_table_id, column_name, old_type, new_type, column_options: dict = {}):
    """
    Updates the data type of a column in a BigQuery table.
    Handles both supported and unsupported data type conversions.
    """
 
    ALLOWED_INT_CONVERSION_TYPES = ["NUMERIC", "BIGNUMERIC", "FLOAT64"]
    ALLOWED_NUMERIC_CONVERSION_TYPES = ["BIGNUMERIC", "FLOAT64"]

    if ((old_type == "INT64" and new_type in ALLOWED_INT_CONVERSION_TYPES) 
        or (old_type in ALLOWED_INT_CONVERSION_TYPES and new_type == "INT64") 
        or (old_type == "NUMERIC" and new_type in ALLOWED_NUMERIC_CONVERSION_TYPES)
        or (old_type in ALLOWED_NUMERIC_CONVERSION_TYPES and new_type == "NUMERIC")): 

        # Use alter column for supported data type conversions
        sql_change_col = f"""ALTER TABLE `{bq_table_id}` ALTER COLUMN {column_name} SET DATA TYPE {new_type}"""
        print(sql_change_col)
        run_bq_command_with_retry(sql_change_col)

    # Need to create and replace column for unsupported data type conversions
    else: 
        # Add temporary column 
        tmp_column_name = f"{column_name}_tmp"

        sql_add_col = f"""ALTER TABLE `{bq_table_id}` 
                        ADD COLUMN {tmp_column_name} {new_type}"""

        # Add required constraint if specified
        if column_options.get("mode", "").upper() == "REQUIRED":
            sql_add_col += "NOT NULL"
        
        # Add description if specified
        if column_options.get("description", ""): 
            sql_add_col += f""" OPTIONS(description="{column_options.get("description")}")"""

        # Copy data from the old column to the new temporary column
        sql_update_col = f"""UPDATE `{bq_table_id}` SET {tmp_column_name} = CAST({column_name} AS {new_type}) WHERE TRUE""" 

        # Drop the old column
        sql_drop_col = f"""ALTER TABLE `{bq_table_id}` DROP COLUMN {column_name}""" 

        # Rename the temporary column to the original column name
        sql_rename_col = f"""ALTER TABLE `{bq_table_id}` RENAME COLUMN {tmp_column_name} TO {column_name}""" 

        full_script = f"{sql_add_col};\n{sql_update_col};\n{sql_drop_col};\n{sql_rename_col}"
        print("Executing multi-step conversion script.")
        run_bq_command_with_retry(full_script)

    return 

def enforce_column_types(bq_client, table_id): 
    """
    Checks and enforces the column types of a BigQuery table against a desired schema defined in a JSON file.
    If a column's type does not match the desired type, it updates accordingly by removing constraints and altering type. 
    """

    # Fetch desired schema from JSON file
    schema_list = json.load(open(f"{current_path}/schemas/{table_id}.json"))

    # Fetch table 
    bq_table_id = bq_client.get_table(f'{config.PROJECT_ID}.{config.BIGQUERY_DATASET}.{table_id}')

    # Convert schema list to dictionary for easy access
    schema_dict = {} 
    for field in schema_list: 
        schema_dict[field['name']] = {"mode": field['mode'], 
                                        "type": field['type'], 
                                        "description": field.get('description', '')}

    # Fetch curent schema from BigQuery
    table_schema = bq_table_id.schema if bq_table_id else []

    # Check fields in the current schema against the desired schema
    for field in table_schema: 
        field_name = field.name 
        field_type = field.field_type 

        # If the field is in the desired schema, check if the type matches
        if field_name in schema_dict: 
            desired_type = schema_dict[field_name]['type']
            if field_type != desired_type: 
                print(f"Updating type of column {field_name} from {field_type} to {desired_type}")
                # Remove any existing constraints before changing the type
                remove_constraint(bq_table_id, field_name)
                # Update the column type
                update_column_type(bq_table_id, field_name, field_type, desired_type, schema_dict[field_name])

def apply_constraints_and_defaults(bq_client, dataset_id, table_id, pk_fk_dict, default_values_dict):
    

    bq_table_id = bq_client.get_table(f'{config.PROJECT_ID}.{dataset_id}.{table_id}')

    # Set primary key and foreign key
    if table_id in pk_fk_dict:
        if pk_fk_dict[table_id]['pk']:
            constraints = bq_table_id._properties.get("tableConstraints") if bq_table_id is not None else None

            # If table exists and primary key already present then skip create primary key command
            if constraints and "primaryKey" in constraints:
                print(f"Skipping the create primary key command , It's already present.")
            else:
                primary_key_sql = f"ALTER TABLE `{config.PROJECT_ID}.{dataset_id}.{table_id}` ADD PRIMARY KEY ({pk_fk_dict[table_id]['pk']}) NOT ENFORCED"
                print(primary_key_sql)
                run_bq_command_with_retry(primary_key_sql)
        
        if pk_fk_dict[table_id]['fk']:
            constraints = bq_table_id._properties.get("tableConstraints") if bq_table_id is not None else None
            foreignKeys_ls = []
            # fetch and create the list for all existing foreignKeys present in the table.
            if constraints and "foreignKeys" in constraints:
                for key in  constraints.get('foreignKeys'):
                    foreignKeys_ls.append(
                            {
                                "column_name": key.get('columnReferences')[0].get('referencingColumn'),
                                "reference_table": key.get('referencedTable').get('tableId'),
                                "reference_column":  key.get('columnReferences')[0].get('referencedColumn')
                            })
                    
            for fk in pk_fk_dict[table_id]['fk']:
                # create foreign key if not exists
                if fk not in foreignKeys_ls: 
                    fk_sql = f"ALTER TABLE `{config.PROJECT_ID}.{dataset_id}.{table_id}` ADD CONSTRAINT fk_{table_id}_{fk['reference_table']} FOREIGN KEY ({fk['column_name']}) REFERENCES `{dataset_id}.{fk['reference_table']}`({fk['reference_column']}) NOT ENFORCED"
                    print(fk_sql)
                    run_bq_command_with_retry(fk_sql)
    
    # Set default values
    if table_id in default_values_dict:
        for default_value  in default_values_dict[table_id]:
            default_value_sql = f"ALTER TABLE `{config.PROJECT_ID}.{dataset_id}.{table_id}` ALTER COLUMN {default_value['col']} SET DEFAULT {default_value['value']}"
            run_bq_command_with_retry(default_value_sql)


def create_table_from_schema(client, table_id):
    
    # Check table is already present or not
    try:
        bq_table_id = client.get_table(
            f"{config.PROJECT_ID}.{config.BIGQUERY_DATASET}.{table_id}"
        )
    except:
        # not present
        bq_table_id = None

    # Create table if table not present
    if not bq_table_id:
        # Create BigQuery table
        clusert_by = ""
        partition_by = ""
        if table_id in part_clus_dict:
            if part_clus_dict[table_id]["cluster"]:
                clusert_by = (
                    f""" --clustering_fields {part_clus_dict[table_id]['cluster']}"""
                )
            if part_clus_dict[table_id]["partition"]:
                partition_by = f""" --time_partitioning_field {part_clus_dict[table_id]['partition']} --time_partitioning_type DAY"""

        # Create table using bq command
        cmd = f"bq mk {partition_by} {clusert_by} --table {config.PROJECT_ID}:{config.BIGQUERY_DATASET}.{table_id}  {current_path}/schemas/{table_id}.json"
        print(cmd)
        os.system(cmd)
        
        # Add short delay to ensure the table is created before applying constraints
        time.sleep(5)
    
        apply_constraints_and_defaults(client, config.BIGQUERY_DATASET, table_id, pk_fk_dict, default_values_dict)

    # If exists, ensure data types and constraints are correct 
    else: 
        # Create a snapshot of the table 
        timestamp = datetime.now().strftime('%Y_%m_%d-%H_%M_%S')
        snapshot_query = f"""
            CREATE SNAPSHOT TABLE `{config.PROJECT_ID}.{config.BIGQUERY_DATASET}.{table_id}_snapshot_{timestamp}`
            CLONE `{config.PROJECT_ID}.{config.BIGQUERY_DATASET}.{table_id}`
            OPTIONS(expiration_timestamp=TIMESTAMP_ADD(CURRENT_TIMESTAMP(), INTERVAL 7 DAY));
        """  
        print("Creating snapshot of the table...") 
        run_bq_command_with_retry(snapshot_query)

        try: 
            print("Enforcing column types...")
            enforce_column_types(client, table_id)
            print("Applying constraints and defaults...")
            apply_constraints_and_defaults(client, config.BIGQUERY_DATASET, table_id, pk_fk_dict, default_values_dict)

        except Exception as e:

            print(f"An error occurred during schema enforcement: {e}")
            print("Restoring table from snapshot...")
            
            full_original_table_id = f"`{config.PROJECT_ID}.{config.BIGQUERY_DATASET}.{table_id}`"
            snapshot_table_ref = f"`{config.PROJECT_ID}.{config.BIGQUERY_DATASET}.{table_id}_snapshot_{timestamp}`"

            # Restore the table by cloning the snapshot back over the original table
            restore_query = f"CREATE OR REPLACE TABLE {full_original_table_id} CLONE {snapshot_table_ref}"
            run_bq_command_with_retry(restore_query)
            
            print("Table restored successfully from snapshot.")

            raise e

        finally:
            drop_snapshot_query = f"""
                DROP SNAPSHOT TABLE `{config.PROJECT_ID}.{config.BIGQUERY_DATASET}.{table_id}_snapshot_{timestamp}`;
                """
            print("Dropping snapshot table...")
            run_bq_command_with_retry(drop_snapshot_query)

def get_dynamic_sql(client, script): 
    client = bigquery.Client()
    query_job = client.query(script).to_dataframe()
    return query_job.iloc[0]

def create_view_from_query(view_query, view_name):
    # Initialize BigQuery client
    client = bigquery.Client()

    # Define the view ID
    view_id = f"{config.PROJECT_ID}.{config.BIGQUERY_DATASET}.{view_name}"

    # Check if the view exists
    try:
        client.get_table(view_id)
        # If the view exists, delete it
        client.delete_table(view_id)
        print(f"Deleted existing view {view_id}")
    except Exception as e:
        print(f"View {view_id} does not exist. Proceeding to create a new one.")

    # Create a View object
    view = bigquery.Table(view_id)
    view.view_query = view_query

    # Create the view
    view = client.create_table(view)

    print(f"Created view {view.project}.{view.dataset_id}.{view.table_id}")


def main():
    client = bigquery.Client()

    create_dataset_if_not_exists()
    create_table_from_schema(client, config.CONSTRUCT_CONNECT_FEED_TABLE)
    create_table_from_schema(client, config.PROJECT_RELEVANCE_TABLE)
    create_table_from_schema(client, config.RANKING_COLUMNS_TABLE)
    create_table_from_schema(client, config.RELEVANT_CATEGORIES_TABLE)
    create_table_from_schema(client, config.RELEVANT_MATERIALS_TABLE)
    create_table_from_schema(client, config.SEARCHES_TERRITORIES_MAP_TABLE)
    create_table_from_schema(client, config.SEARCHES_TERRITORIES_MAP_STAGING_TABLE)
    create_table_from_schema(client, config.SEARCHES_TABLE)
    create_table_from_schema(client, config.SEARCHES_STAGING_TABLE)
    create_table_from_schema(client, config.TERRITORIES_TABLE)
    create_table_from_schema(client, config.TERRITORIES_STAGING_TABLE)
    create_table_from_schema(client, config.ASSIGNED_SEARCH_TABLE)
    create_table_from_schema(client, config.WORKFLOW_FAILURE_EVENTS_TABLE)
    create_table_from_schema(client, config.HIST_DATALOAD_LOG)
    create_table_from_schema(client, config.LATEST_TUNED_LLM_MODEL_TABLE)
    create_table_from_schema(client, config.TUNED_MODEL_PERFORMANCES_TABLE)
    create_table_from_schema(client, config.DODGE_FEED_TABLE)
    create_table_from_schema(client, config.PROJECTS_FOR_DEDUPLICATION_TABLE)
    create_table_from_schema(client, config.LLM_DEDUPLICATION_RESULT_TABLE)
    create_table_from_schema(client, config.PRIMARY_PROJECT_LEAD_TABLE)
    create_table_from_schema(client, config.SOURCE_LINKING_TABLE)
    create_table_from_schema(client, config.COALESCED_PRIMARY_PROJECT_TABLE)
    create_table_from_schema(client, config.CONSOLIDATED_PRIMARY_PROJECT_LEADS_TABLE)
    create_table_from_schema(client, config.PRODUCT_CATEGORY_MATERIALS_MAP_TABLE)
    create_table_from_schema(client, config.SEARCH_PRODUCT_CATEGORY_MAP_TABLE)

if __name__ == "__main__":
    main()
