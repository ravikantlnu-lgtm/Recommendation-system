import unittest
import os
import json
import subprocess
from google.cloud import bigquery
from datetime import datetime, timezone

# Assuming the test script is run from the project root.
# Add the 'bigquery' directory to the path to import its modules.
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'bigquery')))

from build_tables import run_bq_command_with_retry
from remake_table import remake_table
import config_dev as config

# --- Test Configuration ---
TEST_BQ_DATASET = "test_remake_dataset"
TEST_TABLE_ID = "test_remake_table"
REF_TABLE_ORIGINAL_FK = "original_foreign_key"
REF_TABLE_NEW_FK = "new_foreign_key"
FULL_TEST_TABLE_ID = f"{config.PROJECT_ID}.{TEST_BQ_DATASET}.{TEST_TABLE_ID}"
BIGQUERY_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'bigquery'))
SCHEMA_DIR = os.path.join(BIGQUERY_DIR, "schemas")
METADATA_FILE_PATH = os.path.join(BIGQUERY_DIR, "test_tables_metadata_info.json")
SCHEMA_FILE_PATH = os.path.join(SCHEMA_DIR, f"{TEST_TABLE_ID}.json")

class TestRemakeTable(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """
        Set up the test environment before any tests run.
        This involves creating prerequisite tables and configuration files.
        """
        cls.client = bigquery.Client()

        # 1. Create test dataset if it doesn't exist 
        print("Creating test dataset...")
        dataset_id = f"{config.PROJECT_ID}.{TEST_BQ_DATASET}"
        dataset = bigquery.Dataset(dataset_id)
        dataset.location = "US"
        cls.client.create_dataset(dataset, exists_ok=True)

        # 1. Create dummy referenced tables for FK constraints
        
        # Reference table with integer primary key 
        print(f"Creating reference table: {REF_TABLE_ORIGINAL_FK}")
        reference_table_query = f"""
            CREATE OR REPLACE TABLE `{config.PROJECT_ID}.{TEST_BQ_DATASET}.{REF_TABLE_ORIGINAL_FK}`
            (ProjectID INTEGER);
            ALTER TABLE `{config.PROJECT_ID}.{TEST_BQ_DATASET}.{REF_TABLE_ORIGINAL_FK}`
            ADD PRIMARY KEY (ProjectID) NOT ENFORCED;
            INSERT INTO `{config.PROJECT_ID}.{TEST_BQ_DATASET}.{REF_TABLE_ORIGINAL_FK}` VALUES (123);
        """
        run_bq_command_with_retry(reference_table_query)
        
        # Reference table with string primary key
        print(f"Creating reference table: {REF_TABLE_NEW_FK}")
        run_bq_command_with_retry(f"""
            CREATE OR REPLACE TABLE `{config.PROJECT_ID}.{TEST_BQ_DATASET}.{REF_TABLE_NEW_FK}`
            (primary_project_id STRING);
            ALTER TABLE `{config.PROJECT_ID}.{TEST_BQ_DATASET}.{REF_TABLE_NEW_FK}`
            ADD PRIMARY KEY (primary_project_id) NOT ENFORCED;
            INSERT INTO `{config.PROJECT_ID}.{TEST_BQ_DATASET}.{REF_TABLE_NEW_FK}` VALUES ("123");
        """)

        # 2. Create the initial test table with the old schema
        # Columns: time (TIMESTAMP), id (INTEGER), name (STRING)
        print(f"Creating initial test table: {TEST_TABLE_ID}")
        run_bq_command_with_retry(f"""
            CREATE OR REPLACE TABLE `{FULL_TEST_TABLE_ID}` (
                time TIMESTAMP,
                id INTEGER,
                name STRING
            )
            PARTITION BY DATE(time)
            CLUSTER BY id, name
            OPTIONS(
                description="Initial test table"
            );
        """)

        print("Adding constraints to test table...")
        # Primary key "name" of type STRING
        run_bq_command_with_retry(f"ALTER TABLE `{FULL_TEST_TABLE_ID}` ADD PRIMARY KEY (name) NOT ENFORCED")
        # Foreign key "id" of type INTEGER referencing integer ProjectID
        run_bq_command_with_retry(f"""
            ALTER TABLE `{FULL_TEST_TABLE_ID}` ADD FOREIGN KEY (id) 
            REFERENCES `{config.PROJECT_ID}.{TEST_BQ_DATASET}.{REF_TABLE_ORIGINAL_FK}`(ProjectID) NOT ENFORCED
        """)
        
        print("Inserting test data into the initial table...")
        # Insert test data that can be cast correctly later
        run_bq_command_with_retry(f"""
            INSERT INTO `{FULL_TEST_TABLE_ID}` (time, id, name)
            VALUES (CURRENT_TIMESTAMP(), 123, "456")
        """)

        # 3. Create temporary schema and metadata files for the remake process
        os.makedirs(SCHEMA_DIR, exist_ok=True)

        # New schema definition
        # Columns: time (TIMESTAMP), id (STRING), name (INTEGER)
        new_schema = [
            {"name": "time", "type": "TIMESTAMP", "mode": "NULLABLE"},
            {"name": "id", "type": "STRING", "mode": "NULLABLE"},
            {"name": "name", "type": "INTEGER", "mode": "NULLABLE"}
        ]
        with open(SCHEMA_FILE_PATH, "w") as f:
            json.dump(new_schema, f, indent=4)

        # New metadata definition
        # Now want primary key "name" of type INTEGER,  
        # foreign key "id" of type STRING referencing string primary_project_id 
        new_metadata = {
            "partition_cluster_info": {
                TEST_TABLE_ID: {"partition": "time", "cluster": "id,name"}
            },
            "pk_fk_info": {
                TEST_TABLE_ID: {
                    "pk": "name",
                    "fk": [
                        {"column_name": "id", 
                         "reference_table": f"{REF_TABLE_NEW_FK}", 
                         "reference_column": "primary_project_id"}
                    ]
                }
            },
            "default_values_info": {}
        }
        with open(METADATA_FILE_PATH, "w") as f:
            json.dump(new_metadata, f, indent=4)

    @classmethod
    def tearDownClass(cls):
        """Clean up all created resources after tests are done."""
        print("Cleaning up test resources...")

        # Delete test tables 
        cls.client.delete_table(f"{config.PROJECT_ID}.{TEST_BQ_DATASET}.{REF_TABLE_ORIGINAL_FK}", not_found_ok=True)
        cls.client.delete_table(f"{config.PROJECT_ID}.{TEST_BQ_DATASET}.{REF_TABLE_NEW_FK}", not_found_ok=True)
        cls.client.delete_table(f"{FULL_TEST_TABLE_ID}", not_found_ok=True)
        
        # Clean up temporary snapshots if any exist
        for table in cls.client.list_tables(f"{config.PROJECT_ID}.{TEST_BQ_DATASET}"):
            if table.table_id.startswith(f"{TEST_TABLE_ID}_snapshot_"):
                cls.client.delete_table(table.reference, not_found_ok=True)
                print(f"Deleted snapshot: {table.table_id}")

        # Remove test schema and metadata files
        if os.path.exists(SCHEMA_FILE_PATH):
            os.remove(SCHEMA_FILE_PATH)
        if os.path.exists(METADATA_FILE_PATH):
            os.remove(METADATA_FILE_PATH)

    def test_table_remake_and_verification(self):
        """
        Execute the remake_table function and verify the results.
        """

        # Load the created metadata to pass to the function
        with open(METADATA_FILE_PATH, "r") as f:
            metadata = json.load(f)

        # Execute the function under test
        remake_table(
            self.client,
            TEST_BQ_DATASET,
            TEST_TABLE_ID,
            metadata["partition_cluster_info"],
            metadata["pk_fk_info"],
            metadata["default_values_info"]
        )

        # --- Verification ---
        # 1. Verify the new schema
        table = self.client.get_table(FULL_TEST_TABLE_ID)
        schema_map = {field.name: field.field_type for field in table.schema}
        self.assertEqual(schema_map.get("id"), "STRING")
        self.assertEqual(schema_map.get("name"), "INTEGER")
        self.assertEqual(schema_map.get("time"), "TIMESTAMP")

        # 2. Verify partitioning and clustering
        self.assertEqual(table.time_partitioning.field, "time")
        self.assertEqual(table.clustering_fields, ["id", "name"])

        # 2. Verify primary key and foreign key constraints
        constraints = self.client.get_table(FULL_TEST_TABLE_ID)._properties.get("tableConstraints", {})
        primary_constraints = constraints.get("primaryKey")
        assert "name" in primary_constraints["columns"]

        foreign_key  = constraints.get("foreignKeys")[0]
        column_reference = foreign_key.get("columnReferences")[0]
        assert column_reference['referencingColumn'] == "id" 
        assert column_reference['referencedColumn'] == "primary_project_id"

        # 4. Verify data was copied and cast correctly
        query = f"SELECT id, name, time FROM `{FULL_TEST_TABLE_ID}`"
        rows = list(self.client.query(query).result())
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.id, '123')  # Should be a string now
        self.assertEqual(row.name, 456)    # Should be an integer now
        print("Test completed successfully. Table was remade and verified.")

if __name__ == '__main__':
    unittest.main()