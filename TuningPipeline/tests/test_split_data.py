import pytest
import sys
import os
import pandas as pd
import logging
import math
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

from split_data import split_data 
from test_utils import authenticate, make_output_df 

# ------------------------------------------------------------------------------------------------
# Input: configuration file, tests/data/sample_data.csv, tests/data/sample_pool.csv
# Output: Output[Dataset] of split data -- Saved to "tmp/X_train.csv", "tmp/y_train.csv", "tmp/X_valid.csv", "tmp/y_valid.csv", "tmp/X_test.csv", "tmp/y_test.csv"
# ------------------------------------------------------------------------------------------------

# Mock the read_csv to return files from tmp directory
def create_mock_read_csv():
    """ 
    This function creates a mock for pd.read_csv to return the preprocessed data and pool data from local files, instead of GCS.
    """

    original_read_csv = pd.read_csv

    def mock_read_csv(filepath, *args, **kwargs):
        filename = os.path.basename(filepath)  # Extract the file name
        if filename == "preprocessed_data.csv":
            return original_read_csv("tests/data/sample_data.csv", *args, **kwargs)
        elif filename == "pool_data.csv":
            return original_read_csv("tests/data/sample_pool.csv", *args, **kwargs)
        else: 
            raise ValueError(f"Unexpected file path: {filepath}")

    return mock_read_csv

@pytest.fixture
def mock_upload_fixture(mocker):
    """
    This function patches the upload to GCS function to avoid actual upload to GCS. 
    It returns instead the local file name that would be uploaded.
    """
    mock_upload = mocker.patch("utils.upload_file_to_gcs")
    mock_upload.side_effect = lambda local_file_path, bucket_name, blob_name: f'{local_file_path}'
    return mock_upload

# This fixture declares the different parameters to be used in test_format_data_split_similarity test.
@pytest.mark.parametrize(
        "similarity_threshold, max_test_size_reduction, should_fail",
        [
            (1, 0.99, False),  # High similarity threshold and high reduction, expect no pool data to be used
            (0.8, 0.9, False),  # Lower similarity threshold and high reduction, expect some pool data to be used
            (0, 0, True),  # Low similarity threshold and no reduction, should raise an error
        ]
)
def test_format_data_split_similarity(mocker, mock_upload_fixture, 
                                    similarity_threshold, max_test_size_reduction, should_fail, caplog, tmp_path):
    """ 
    This function tests the split by similarity functionality on the split_data component. 

    It uses different parameters declared above to test the behavior of the function under different conditions.
    
    The test checks if the output files are created and if the sizes of the test datasets are as expected.
    """
    
    caplog.set_level(logging.INFO)

    # Read the configuration file 
    config_path = os.path.join(parent_dir, "configs/dev_a_4_e_10.json")
    with open(config_path, "r") as config_file:
        config = json.load(config_file)

    authenticate(config["project_id"], config["location"])

    # Patch download function to avoid actual download from GCS
    mocker.patch("utils.download_file_from_gcs")

    # Patch pd.read_csv to return local files instead of GCS
    original_read_csv = pd.read_csv
    mock_read_csv = create_mock_read_csv()
    mocker.patch("pandas.read_csv", side_effect=mock_read_csv)

    # Set up input dataset paths from our sample data
    dataset_gcs_uri = "tests/data/sample_data.csv"
    pool_gcs_uri = "tests/data/sample_pool.csv"

    # Create temporary output paths for Output[Dataset]
    X_train_path = tmp_path / "X_train.csv"
    y_train_path = tmp_path / "y_train.csv"
    X_valid_path = tmp_path / "X_valid.csv"
    y_valid_path = tmp_path / "y_valid.csv"
    X_test_path = tmp_path / "X_test.csv"
    y_test_path = tmp_path / "y_test.csv"
    X_train_output = make_output_df(str(X_train_path))
    y_train_output = make_output_df(str(y_train_path))
    X_valid_output = make_output_df(str(X_valid_path))
    y_valid_output = make_output_df(str(y_valid_path))
    X_test_output = make_output_df(str(X_test_path))
    y_test_output = make_output_df(str(y_test_path))

    # Ensure the failure case is handled
    if should_fail: 
        with pytest.raises(ValueError, match = "Not enough test data points. Ending pipeline run."): 
            split_data.python_func(
                project_id=config["project_id"],
                bucket=config["bucket"],
                dataset_gcs_uri=dataset_gcs_uri,
                pool_gcs_uri=pool_gcs_uri,
                id_col=config["id_col"],
                search_id_col=config["search_id_col"],
                territory_id_col=config["territory_id_col"], 
                response_col=config["response_col"],
                training_split=config["training_split"],
                validation_split=config["validation_split"], 
                split_by_similarity=True,
                similarity_threshold=similarity_threshold,
                max_test_size_reduction=max_test_size_reduction,
                column_types=config["column_types"],
                sentence_transformer_name=config["sentence_transformer_name"],
                random_state=config["seed"],
                X_train_output=X_train_output,
                y_train_output=y_train_output,
                X_valid_output=X_valid_output,
                y_valid_output=y_valid_output,
                X_test_output=X_test_output,
                y_test_output=y_test_output
            )
    else: 
        # Run the function with the remaining parameters
        outputs = split_data.python_func(
        project_id=config["project_id"],
        bucket=config["bucket"],
        dataset_gcs_uri=dataset_gcs_uri,
        pool_gcs_uri=pool_gcs_uri,
        id_col=config["id_col"],
        search_id_col=config["search_id_col"],
        territory_id_col=config["territory_id_col"], 
        response_col=config["response_col"],
        training_split=config["training_split"],
        validation_split=config["validation_split"], 
        split_by_similarity=True,
        similarity_threshold=similarity_threshold,
        max_test_size_reduction=max_test_size_reduction,
        column_types=config["column_types"],
        sentence_transformer_name=config["sentence_transformer_name"],
        random_state=config["seed"],
        X_train_output=X_train_output,
        y_train_output=y_train_output,
        X_valid_output=X_valid_output,
        y_valid_output=y_valid_output,
        X_test_output=X_test_output,
        y_test_output=y_test_output
        )

        print(record.message for record in caplog.records)

        assert X_train_path.exists(), "X_train file was not created"
        assert y_train_path.exists(), "y_train file was not created"
        assert X_valid_path.exists(), "X_valid file was not created"
        assert y_valid_path.exists(), "y_valid file was not created"        
        assert X_test_path.exists(), "X_test file was not created"
        assert y_test_path.exists(), "y_test file was not created"

        # Check the output test datasets
        X_test = original_read_csv(X_test_path)
        y_test = original_read_csv(y_test_path)

        original_sample_data = original_read_csv('tests/data/sample_data.csv')

        min_sample_test_size = len(original_sample_data) * (1-config["training_split"]) * (1-max_test_size_reduction)
        assert len(X_test) >= math.floor(min_sample_test_size), f"X_test size {len(X_test)} is less than the minimum sample test size {min_sample_test_size}"
        assert len(y_test) >= math.floor(min_sample_test_size), f"y_test size {len(y_test)} is less than the minimum sample test size {min_sample_test_size}"


def test_format_data_regular_split(mocker, mock_upload_fixture, caplog, tmp_path):
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
    mocker.patch("utils.download_file_from_gcs")

    # Patch pd.read_csv to return local files instead of GCS
    original_read_csv = pd.read_csv
    mock_read_csv = create_mock_read_csv()
    mocker.patch("pandas.read_csv", side_effect=mock_read_csv)

    # Set up input dataset paths
    dataset_gcs_uri = "tests/data/sample_data.csv"
    pool_gcs_uri = "tests/data/sample_pool.csv"

    # Create temporary output paths for Output[Dataset]
    X_train_path = tmp_path / "X_train.csv"
    y_train_path = tmp_path / "y_train.csv"
    X_valid_path = tmp_path / "X_valid.csv"
    y_valid_path = tmp_path / "y_valid.csv"
    X_test_path = tmp_path / "X_test.csv"
    y_test_path = tmp_path / "y_test.csv"
    X_train_output = make_output_df(str(X_train_path))
    y_train_output = make_output_df(str(y_train_path))
    X_valid_output = make_output_df(str(X_valid_path))
    y_valid_output = make_output_df(str(y_valid_path))
    X_test_output = make_output_df(str(X_test_path))
    y_test_output = make_output_df(str(y_test_path))

    # Run the function
    outputs = split_data.python_func(
        project_id=config["project_id"],
        bucket=config["bucket"],
        dataset_gcs_uri=dataset_gcs_uri,
        pool_gcs_uri=pool_gcs_uri,
        id_col=config["id_col"],
        search_id_col=config["search_id_col"],
        territory_id_col=config["territory_id_col"], 
        response_col=config["response_col"],
        training_split=config["training_split"],
        validation_split=config["validation_split"], 
        split_by_similarity=False,
        similarity_threshold=config["similarity_threshold"],
        max_test_size_reduction= config["max_test_size_reduction"],
        column_types=config["column_types"],
        sentence_transformer_name=config["sentence_transformer_name"],
        random_state=config["seed"],
        X_train_output=X_train_output,
        y_train_output=y_train_output,
        X_valid_output=X_valid_output,
        y_valid_output=y_valid_output,
        X_test_output=X_test_output,
        y_test_output=y_test_output
        )

    print(record.message for record in caplog.records)

    assert X_train_path.exists(), "X_train file was not created"
    assert y_train_path.exists(), "y_train file was not created"
    assert X_valid_path.exists(), "X_valid file was not created"
    assert y_valid_path.exists(), "y_valid file was not created"        
    assert X_test_path.exists(), "X_test file was not created"
    assert y_test_path.exists(), "y_test file was not created"
