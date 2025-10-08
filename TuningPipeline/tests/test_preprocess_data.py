import pytest
import sys
import os
import pandas as pd
import logging
import kfp 
from kfp.dsl import component, Output, Dataset
import typing 
import json
from unittest.mock import MagicMock 
import tempfile
from unittest.mock import patch

# Import component
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))  # Parent directory
components_dir = os.path.join(parent_dir, "components")  # Components directory
sys.path.insert(0, parent_dir)  # Add parent directory to sys.path
sys.path.insert(0, components_dir)  # Add components directory to sys.path

from preprocess_data import preprocess_data
from test_utils import authenticate, unprocessed_data

# ------------------------------------------------------------------------------------------------
# Input: configuration file, tests/data/unprocessed_data.csv 
# Output: Output[Dataset] of preprocessed data -- Saved to "tmp/data.csv" and "tmp/pool.csv"
# ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("clustering_enabled", [True, False]) # Test with clustering enabled and disabled
def test_preprocess_data(mocker, caplog, unprocessed_data, clustering_enabled):

    caplog.set_level(logging.INFO)# Create temporary output paths for Dataset

    config_path = os.path.join(parent_dir, "configs/dev_a_4_e_10.json")
    with open(config_path, "r") as config_file:
        config = json.load(config_file)

    authenticate(config["project_id"], config["location"])

    # Patch upload function to avoid actual upload to GCS 
    mock_upload = mocker.patch("utils.upload_file_to_gcs")
    mock_upload.side_effect = lambda local_file_path, bucket_name, blob_name: f'{local_file_path}' # Return local file instead

    # Declare columns to rank
    ranking_cols = [
        "Title",
        'Materials_Material',
        'RSMeansMaterialDivisions_Division_ThermalandMoistureProtection',
        'DocumentAvailability_Plans',
        'Parameters_Parameter_Ownership',
        'Details_Detail_Scope',
        'Parameters_Parameter_WorkType',
        'Details_Detail',
        'Stage',
        'DocumentAvailability_Specs',
        'ParentCategories_ParentCategory',
        'ParentCategories_PrimaryCategoryName',
        'Valuation_Value',
        'Parameters_Parameter_Structures',
        'Details_Detail_Notes',
        'RSMeansMaterialDivisions_Division_Masonry',
        'DocumentAvailability_Addenda',
        'Addresses_Address',
        'RSMeansMaterialDivisions_Division_Finishes',
        'RSMeansMaterialDivisions_Division_Openings',
        'RSMeansMaterialDivisions_Division_Metals']
        
    output = preprocess_data.python_func(
        project_id=config["project_id"],
        bucket=config["bucket"],
        uuid="testing_uuid",
        id_col=config["id_col"],
        search_id_col=config["search_id_col"],
        search_name_col=config["search_name_col"],
        query_col=config["query_col"],
        territory_id_col=config["territory_id_col"],
        territory_distance_col=config["territory_distance_col"],
        materials_valuation_col=config["materials_valuation_col"],
        response_col=config["response_col"],
        ranking_cols=ranking_cols,
        dataset=unprocessed_data,  # Use the unprocessed data fixture
        max_diff=config["max_diff"],
        output_filename=config["data_output_filename"],
        max_sample_size=config["max_sample_size"],
        clustering=clustering_enabled,
        clustering_inf=config["clustering_inf"],
        column_types=config["column_types"],
        sentence_transformer_name=config["sentence_transformer_name"],
        random_state=config["seed"]
    )

    print(record.message for record in caplog.records)

    dataset_tmp_file = output.dataset_gcs_uri
    pool_tmp_file = output.pool_gcs_uri

    clustered = config['clustering']

    assert dataset_tmp_file == "tmp/data.csv", f"Dataset GCS URI is not correct: {dataset_tmp_file}"
    df = pd.read_csv(dataset_tmp_file)
    assert df is not None, "DataFrame is None"
    
    if clustered: 
        assert pool_tmp_file == "tmp/pool.csv", f"Pool GCS URI is not correct: {pool_tmp_file}"
        pool = pd.read_csv(pool_tmp_file)
        assert pool is not None, "Pool DataFrame is None"
    
    cols = [config["id_col"], config["search_id_col"], 
            config["search_name_col"], config["query_col"], 
            config["territory_id_col"], config["territory_distance_col"], 
            config["materials_valuation_col"],
            config["response_col"]]
    cols += ranking_cols
    
    # Check that all columns are exactly the same
    expected_columns = set(cols)
    actual_columns = set(df.columns)
    assert expected_columns == actual_columns, f"Column mismatch. Expected: {expected_columns}, Actual: {actual_columns}"
    
    if clustered:
        pool_columns = set(pool.columns)
        assert expected_columns == pool_columns, f"Pool column mismatch. Expected: {expected_columns}, Actual: {pool_columns}"
    
    original_data = pd.read_csv('tests/data/unprocessed_data.csv')
    assert len(df) <= len(original_data), "DataFrame data is not smaller than original data"
    if clustered: 
        assert len(pool) <=len(original_data), "Pool data is not smaller than original data"
    

