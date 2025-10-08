import pytest
import sys
import os
import pandas as pd
import logging
import kfp 
from kfp.dsl import component, Output, Dataset
import typing 
import json
from unittest.mock import MagicMock, patch
import tempfile
import os

# Import component
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))  # Parent directory
components_dir = os.path.join(parent_dir, "components")  # Components directory
sys.path.insert(0, parent_dir)  # Add parent directory to sys.path
sys.path.insert(0, components_dir)  # Add components directory to sys.path

from evaluate_model import evaluate_model
from test_utils import authenticate, y_test_df

# ------------------------------------------------------------------------------------------------
# Input: configuration file, tests/data/formatted_testing_data.jsonl (from test_formatted_tuning_data), tests/data/y_test.csv
# Output: dictionary of performance metrics for base model and tuned model
# ------------------------------------------------------------------------------------------------

# Mock the read_csv to return files from tests/data directory
def create_mock_read_csv():
    """ 
    This function creates a mock for pd.read_csv to return the formatted testing data from local files, instead of GCS.
    """

    original_read_csv = pd.read_csv

    def mock_read_csv(filepath, *args, **kwargs):
        # Handle both string filepaths and file objects
        if hasattr(filepath, 'name'):
            # It's a file object, get the filename from the name attribute
            filename = os.path.basename(filepath.name)
        else:
            # It's a string filepath
            filename = os.path.basename(filepath)
            
        if "formatted_testing_data.jsonl" in filename:
            return original_read_csv("tests/data/formatted_testing_data.jsonl", *args, **kwargs)
        else: 
            # For other files, use the original read_csv function
            return original_read_csv(filepath, *args, **kwargs)

    return mock_read_csv

def test_evaluate_model(mocker, caplog, y_test_df):

    caplog.set_level(logging.INFO)# Create temporary output paths for Dataset

    config_path = os.path.join(parent_dir, "configs/dev_a_4_e_10.json")
    with open(config_path, "r") as config_file:
        config = json.load(config_file) 

    authenticate(config["project_id"], config["location"])

    mocker.patch("utils.download_file_from_gcs")

    # Patch pd.read_csv to return local files instead of GCS
    original_read_csv = pd.read_csv
    mock_read_csv = create_mock_read_csv()
    mocker.patch("pandas.read_csv", side_effect=mock_read_csv)
    
    # Set up input dataset paths from our sample data
    X_test_formatted_gcs_uri = f"formatted_testing_data.jsonl"

    # Tuned model endpoint from previous pipeline
    tuned_model_endpoint = "projects/195063057478/locations/us-central1/endpoints/6903135320921866240"
    base_model = "gemini-2.5-flash"

    output_dict = evaluate_model.python_func(
        project_id=config["project_id"],
        location=config["location"],
        bucket=config["bucket"],
        id_col=config["id_col"],
        response_col=config["response_col"],
        base_model=base_model,
        tuned_model_endpoint=tuned_model_endpoint,
        X_test_formatted_gcs_uri=X_test_formatted_gcs_uri,
        y_test=y_test_df,
        labels=config["labels"]
    )

    assert type(output_dict.performance_metrics == dict), "Performance metrics should be a dictionary"
    assert output_dict.base_model == base_model, "Base model name should match"
    assert output_dict.tuned_model == tuned_model_endpoint, "Tuned model name should match"
    print(output_dict)

    print(record.message for record in caplog.records)