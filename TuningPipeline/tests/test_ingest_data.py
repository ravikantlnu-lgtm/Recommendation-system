import pytest
import sys
import os
import pandas as pd
import logging
import kfp 
from kfp.dsl import component, Output, Dataset
import json
import shutil

# Import component
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))  # Parent directory
components_dir = os.path.join(parent_dir, "components")  # Components directory
sys.path.insert(0, parent_dir)  # Add parent directory to sys.path
sys.path.insert(0, components_dir)  # Add components directory to sys.path

# Copy dynamics_manager.py from the source directory to the current directory
source_path = os.path.abspath(os.path.join(parent_dir, "../CloudFunction/services/dynamics_manager.py"))
destination_path = os.path.join(current_dir, "../dynamics_manager.py")

try:
    shutil.copy(source_path, destination_path)
    logging.info(f"Copied dynamics_manager.py from {source_path} to {destination_path}")
except FileNotFoundError:
    logging.error(f"Source file not found: {source_path}")

from ingest_data import ingest_data
from test_utils import make_output_df, authenticate

# ------------------------------------------------------------------------------------------------
# Input: configuration file
# Output: Output[Dataset] of ingested project data from CRM -- Saved to "tmp/dataset.csv"
# ------------------------------------------------------------------------------------------------

def test_ingest_data(caplog, tmp_path):

    caplog.set_level(logging.INFO) 

    # Create temporary output paths for Dataset
    dataset_path = tmp_path / "dataset.csv"
    dataset = make_output_df(str(dataset_path))

    config_path = os.path.join(parent_dir, "configs/dev_a_4_e_10.json")
    with open(config_path, "r") as config_file:
        config = json.load(config_file)

    authenticate(config["project_id"], config["location"])

    _ = ingest_data.python_func(
        project_id=config["project_id"],
        location=config["location"],
        dm_instance_url=config["dm_instance_url"],
        bq_dataset=config["bq_dataset"],
        id_col=config["id_col"],
        search_id_col=config["search_id_col"],
        search_name_col=config["search_name_col"],
        query_col=config["query_col"],
        territory_id_col=config["territory_id_col"],
        territory_distance_col=config["territory_distance_col"],
        materials_valuation_col=config["materials_valuation_col"],
        response_col=config["response_col"],
        boolean_filters_bq_table=config["boolean_filters_bq_table"],
        ranking_cols_bq_table=config["ranking_cols_bq_table"],
        coalesced_projects_bq_table=config["coalesced_projects_bq_table"],
        dataset=dataset,
    )

    print(record.message for record in caplog.records)

    # Assert dataset file was created in tmp/dataset.csv
    assert dataset_path.exists(), "Dataset file was not created"

    # Read dataset file
    output_df = pd.read_csv(dataset_path)

    print("Output DataFrame:")
    print(output_df.head())

    # Assert columns are available in data
    cols = [config['id_col'], config['search_id_col'], config['search_name_col'], config['query_col'], 
            config['territory_id_col'], config['territory_distance_col'], config['materials_valuation_col'], 
            config['response_col']]
    for col in cols:
        assert col in output_df.columns, f"Column {col} not found in output DataFrame"

    all_cols = [] 
    items = config['column_types'].values()
    for item in items: 
        all_cols += item

    # Ensure all of the columns for ranking are present
    for col in all_cols: 
        assert col in output_df.columns, f"Column {col} not found in output DataFrame"