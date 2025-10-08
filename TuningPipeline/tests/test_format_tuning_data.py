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
from unittest.mock import patch
import shutil

# Import component
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))  # Parent directory
components_dir = os.path.join(parent_dir, "components")  # Components directory
sys.path.insert(0, parent_dir)  # Add parent directory to sys.path
sys.path.insert(0, components_dir)  # Add components directory to sys.path

from format_tuning_data import format_tuning_data
from test_utils import authenticate, X_train_df, y_train_df, X_valid_df, y_valid_df, X_test_df, y_test_df

# ------------------------------------------------------------------------------------------------
# Input: configuration file, tests/data/X_train.csv, tests/data/y_train.csv, tests/data/X_valid.csv, tests/data/y_valid.csv, tests/data/X_test.csv, tests/data/y_test.csv
# Output: Output[Dataset] of formatted data -- Saved to "tmp/formatted_training_data.jsonl", "tmp/formatted_validation_data.jsonl", "tmp/formatted_testing_data.jsonl"
# ------------------------------------------------------------------------------------------------

@pytest.fixture
def mock_upload_fixture(mocker):
    """
    This function patches the upload to GCS function to avoid actual upload to GCS. 
    It returns instead the local file name that would be uploaded.
    """
    mock_upload = mocker.patch("utils.upload_file_to_gcs")
    mock_upload.side_effect = lambda local_file_path, bucket_name, blob_name: f'{local_file_path}'
    return mock_upload

def check_formatted_lines(lines, test_type: str): 
    """
    This function checks the formatted training/validation lines. 
    It ensures that each line is a valid JSON object and contains the expected keys/values.
    """
    for row in lines:
        record = json.loads(row)
        assert "contents" in record, "Missing 'contents' key in record"

        contents = record["contents"]

        if test_type == "training" or test_type == "validation": 
            assert isinstance(contents, list), "'contents' should be a list"
            assert len(contents) == 2, "'contents' list should have two elements, user and model"

            user_dict = contents[0]
            model_dict = contents[1]
            assert isinstance(user_dict, dict), "'user' should be a dictionary"
            assert isinstance(model_dict, dict), "'model' should be a dictionary"
            assert "role" in user_dict, "Missing 'role' key in user dictionary"
            assert "parts" in user_dict, "Missing 'content' key in user dictionary"
            assert "role" in model_dict, "Missing 'role' key in model dictionary"
            assert "parts" in model_dict, "Missing 'content' key in model dictionary"
        else: 
            assert isinstance(contents, list), "'contents' should be a list" 
            assert len(contents) == 1, "'contents' list should have one element, text input" 
            assert isinstance(contents[0], str), "'contents' should be a string prompt"

    return

def test_format_data(mocker, mock_upload_fixture, caplog, X_train_df, y_train_df, X_valid_df, y_valid_df, X_test_df, y_test_df):
    """ 
    This function tests the regular split functionality on the format_tuning_data component.
    """
    
    caplog.set_level(logging.INFO)

    # Read the configuration file 
    config_path = os.path.join(parent_dir, "configs/dev_a_4_e_10.json")
    with open(config_path, "r") as config_file:
        config = json.load(config_file)

    authenticate(config["project_id"], config["location"])
    # Patch download function to avoid actual download from GCS
    # Used to fetch the train, test, and validation data from our test data directory
    mock_upload = mocker.patch("utils.upload_file_to_gcs")
    mock_upload.side_effect = lambda local_file_path, bucket_name, blob_name: f'{local_file_path}' # Return local file instead

    # Run the function
    outputs = format_tuning_data.python_func(
        project_id=config["project_id"],
        bucket=config["bucket"],
        uuid="test-uuid",
        prompt = config["prompt"],
        id_col=config["id_col"],
        search_id_col=config["search_id_col"],
        search_name_col=config["search_name_col"],
        query_col=config["query_col"],
        territory_id_col=config["territory_id_col"],
        materials_valuation_col=config["materials_valuation_col"],
        bq_dataset=config["bq_dataset"],
        territory_table=config["territories_bq_table"],
        search_product_map_table=config["search_product_map_bq_table"],
        cc_feed_table=config["cc_bq_table"],
        dodge_feed_table=config["dodge_bq_table"],
        consolidated_projects_bq_table=config["consolidated_projects_bq_table"],
        sales_project_id=config["sales_project_id"],
        sales_dataset=config["sales_bq_dataset"],
        sales_table=config["sales_table"],
        customer_table=config["sales_customer_table"],
        X_train=X_train_df, 
        y_train=y_train_df,
        X_valid=X_valid_df,
        y_valid=y_valid_df,
        X_test=X_test_df,
        y_test=y_test_df,
        output_filename = config["formatted_data_output_filename"],
        historical_days=1, # Set to 1 to limit queries in the prompt
    )
        
    print(record.message for record in caplog.records)

    training_dataset_uri = outputs.formatted_training_dataset_gcs_uri
    validation_dataset_uri = outputs.formatted_validation_dataset_gcs_uri
    testing_dataset_uri = outputs.formatted_testing_dataset_gcs_uri

    assert training_dataset_uri == "tmp/formatted_training_data.jsonl", "Training dataset GCS URI is not correct"
    assert validation_dataset_uri == "tmp/formatted_validation_data.jsonl", "Validation dataset GCS URI is not correct"
    assert testing_dataset_uri == "tmp/formatted_testing_data.jsonl", "Testing dataset GCS URI is not correct"

    # Read the jsonl lines 
    with open(training_dataset_uri, 'r') as f:
        training_lines = f.readlines()
    with open(validation_dataset_uri, 'r') as f:
        validation_lines = f.readlines()
    with open(testing_dataset_uri, 'r') as f:
        testing_lines = f.readlines()

    check_formatted_lines(training_lines, "training")
    check_formatted_lines(validation_lines, "validation")
    check_formatted_lines(testing_lines, "testing")
    
    # Save formatted testing data to tests/data directory for evaluation tests
    tests_data_dir = os.path.join(current_dir, "data")
    os.makedirs(tests_data_dir, exist_ok=True)  
    
    formatted_testing_data_path = os.path.join(tests_data_dir, "formatted_testing_data.jsonl")
    shutil.copy(testing_dataset_uri, formatted_testing_data_path)
    
    logging.info(f"Saved formatted testing data to: {formatted_testing_data_path}")
