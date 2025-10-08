import json
import os
import argparse

# import queries
from google.cloud import bigquery
from datetime import datetime

from build_tables import run_bq_command_with_retry, apply_constraints_and_defaults

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

def remake_table(client: bigquery.Client, dataset_id: str, table_id: str, part_clus_dict: dict, pk_fk_dict: dict, default_values_dict: dict): 
    """
    This function remakes a BigQuery table by:
        1. Creating a snapshot of the existing table.
        2. Dropping the original table.
        3. Creating a new table with the newest schema and same ID.
        4. Applying primary keys, foreign keys, and default values to new table. 
        5. Copying data from the snapshot to the new table with type casting to ensure correct schema.
        6. If successful, drop snapshot table. Else, restore the original table from the snapshot and drop the snapshot table.

    Args: 
    - client (bigquery.Client): The BigQuery client to use for operations.
    - dataset_id (str): The ID of the dataset containing the table.
    - table_id (str): The ID of the table to remake.
    - part_clus_dict (dict): Dictionary containing partition and clustering information for tables.
    - pk_fk_dict (dict): Dictionary containing primary key and foreign key information for tables.
    - default_values_dict (dict): Dictionary containing default values for table columns.
    """

    full_table_id = f"{config.PROJECT_ID}.{dataset_id}.{table_id}"

    # Check if the table exists
    try: 
        client.get_table(full_table_id)
    except Exception as e:
        print(f"Error getting table {table_id}: {e}")
        return 
    
    print(f"Remaking table {table_id}...")

    # Create a snapshot of the table for safety
    timestamp = datetime.now().strftime('%Y_%m_%d-%H_%M_%S')
    snapshot_id = f"{config.PROJECT_ID}.{dataset_id}.{table_id}_snapshot_{timestamp}"
    snapshot_query = f"""
        CREATE SNAPSHOT TABLE `{snapshot_id}`
        CLONE `{full_table_id}`
        OPTIONS(expiration_timestamp=TIMESTAMP_ADD(CURRENT_TIMESTAMP(), INTERVAL 1 DAY));
    """  
    print("Creating snapshot of the table...") 
    run_bq_command_with_retry(snapshot_query)

    try: 
        # Drop the original table
        print("Dropping the original table...")
        drop_query = f"""DROP TABLE IF EXISTS `{full_table_id}`"""
        run_bq_command_with_retry(drop_query)

        # Create new table with schema
        print("Creating new table with schema...")
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
        cmd = f"bq mk {partition_by} {clusert_by} --table {config.PROJECT_ID}:{dataset_id}.{table_id}  {current_path}/schemas/{table_id}.json"
        print(cmd)
        os.system(cmd)

        # Apply primary keys, foreign keys, and default values
        print("Applying constraints and default values of new table...")
        apply_constraints_and_defaults(client, dataset_id, table_id, pk_fk_dict, default_values_dict)

        # Get the schema of the new table
        print("Fetching the schema of the new table...")
        new_table = client.get_table(full_table_id)
        schema_fields = new_table.schema 

        # Prepare the select clause with type casting
        # Used to ensure that the data types match the new table schema
        select_expressions = [f"CAST({field.name} AS {field.field_type}) AS {field.name}" for field in schema_fields]
        select_clause = ", ".join(select_expressions)

        # Copy data from the snapshot to the new table 
        print("Copying data from the snapshot table to the new table...")
        copy_query = f"""INSERT INTO `{full_table_id}` SELECT {select_clause} FROM `{snapshot_id}`"""
        print(copy_query)
        run_bq_command_with_retry(copy_query)

    except Exception as e:

        print(f"Error during table remake process: {e}")
        
        # If an error occurs, restore the table from the snapshot
        restore_query = f"""
            CREATE OR REPLACE TABLE `{full_table_id}`
            CLONE `{snapshot_id}`
        """
        run_bq_command_with_retry(restore_query)

    finally:

        # Drop snapshot table 
        drop_snapshot_query = f"""DROP SNAPSHOT TABLE `{config.PROJECT_ID}.{dataset_id}.{table_id}_snapshot_{timestamp}`"""
        print("Dropping snapshot table...")
        run_bq_command_with_retry(drop_snapshot_query)
        
        return


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Remake a BigQuery table")
    parser.add_argument("dataset_id", type=str, help="The ID of the dataset containing the table", default=config.BIGQUERY_DATASET)
    parser.add_argument("table_id", type=str, help="The ID of the table to remake")
    args = parser.parse_args()

    # Initialize BigQuery client
    client = bigquery.Client()

    # Remake the specified table
    remake_table(client, args.dataset_id, args.table_id, part_clus_dict, pk_fk_dict, default_values_dict)