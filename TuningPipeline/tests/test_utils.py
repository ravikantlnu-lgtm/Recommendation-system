from kfp.dsl import component, Output, Dataset
import typing
import pytest 
import pandas as pd

from google.cloud import storage, aiplatform, secretmanager
import typing
from kfp.dsl import Dataset
import os
import tempfile

def make_output_df(uri: str):
    class TestArtifact(Dataset):
        def __init__(self, uri: str):
            self.uri = uri
            self.path = uri  # Mock the `path` attribute for testing

    return TestArtifact(uri)

def authenticate(project_id: str, location: str):
    
    # Authenticate with Google Cloud
    aiplatform.init(project=project_id, location=location)

    env_file = os.getenv('ENV_FILE', default='.env.DEV')

    # Path to your service account key file
    if env_file == ".env.DEV":
        service_account_key_path = "dev_key.json"
    elif env_file == ".env.PROD":
        service_account_key_path = "prod_key.json"
    
    # Set GOOGLE_APPLICATION_CREDENTIALS environment variable
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = service_account_key_path
    
    return


# Makes a test artifact (df) for testing
def make_test_artifact(artifact_type: typing.Type):
    class TestArtifact(artifact_type):
        def _get_path(self):
            return super()._get_path() or self.uri

    return TestArtifact

@component()
def unprocessed_df_component(dataset: Output[Dataset]):

    df = pd.read_csv("tests/data/unprocessed_data.csv")
    os.makedirs("tmp", exist_ok=True)
    dataset.path = "tmp/unprocessed_data.csv"
    df.to_csv(dataset.path, index=False)

    return


# Creates a sample input df for the preprocess_data component
@pytest.fixture
def unprocessed_data():

    os.makedirs("tmp", exist_ok=True)
    output_path = "tmp/local_unprocessed_data.csv"
    sample_df_artifact = make_test_artifact(Dataset)(output_path)
    unprocessed_df_component.python_func(dataset=sample_df_artifact)

    return sample_df_artifact

# --

@component()
def X_train_component(dataset: Output[Dataset]):

    df = pd.read_csv("tests/data/X_train.csv")
    os.makedirs("tmp", exist_ok=True)
    dataset.path = "tmp/X_train.csv"
    df.to_csv(dataset.path, index=False)
    return

# Creates a sample input df
@pytest.fixture
def X_train_df():

    os.makedirs("tmp", exist_ok=True)
    output_path = "tmp/local_x_train_df.csv"
    sample_df_artifact = make_test_artifact(Dataset)(output_path)
    X_train_component.python_func(dataset=sample_df_artifact)

    return sample_df_artifact


@component()
def y_train_component(dataset: Output[Dataset]):

    df = pd.read_csv("tests/data/y_train.csv")
    os.makedirs("tmp", exist_ok=True)
    dataset.path = "tmp/y_train_df.csv"
    df.to_csv(dataset.path, index=False)

    return

@pytest.fixture
def y_train_df():

    os.makedirs("tmp", exist_ok=True)
    output_path = "tmp/local_y_train_df.csv"
    sample_df_artifact = make_test_artifact(Dataset)(output_path)
    y_train_component.python_func(dataset=sample_df_artifact)

    return sample_df_artifact 


# --

@component()
def X_valid_component(dataset: Output[Dataset]):

    df = pd.read_csv("tests/data/X_valid.csv")
    os.makedirs("tmp", exist_ok=True)
    dataset.path = "tmp/X_valid.csv"
    df.to_csv(dataset.path, index=False)
    return

# Creates a sample input df
@pytest.fixture
def X_valid_df():

    os.makedirs("tmp", exist_ok=True)
    output_path = "tmp/local_x_valid_df.csv"
    sample_df_artifact = make_test_artifact(Dataset)(output_path)
    X_valid_component.python_func(dataset=sample_df_artifact)

    return sample_df_artifact


@component()
def y_valid_component(dataset: Output[Dataset]):

    df = pd.read_csv("tests/data/y_valid.csv")
    os.makedirs("tmp", exist_ok=True)
    dataset.path = "tmp/y_valid_df.csv"
    df.to_csv(dataset.path, index=False)

    return

@pytest.fixture
def y_valid_df():

    os.makedirs("tmp", exist_ok=True)
    output_path = "tmp/local_y_valid_df.csv"
    sample_df_artifact = make_test_artifact(Dataset)(output_path)
    y_train_component.python_func(dataset=sample_df_artifact)

    return sample_df_artifact 
# -----

@component()
def X_test_component(dataset: Output[Dataset]):

    df = pd.read_csv("tests/data/X_test.csv")
    os.makedirs("tmp", exist_ok=True)
    dataset.path = "tmp/x_test_df.csv"
    df.to_csv(dataset.path, index=False)
    return

# Creates a sample input df
@pytest.fixture
def X_test_df():

    os.makedirs("tmp", exist_ok=True)
    output_path = "tmp/local_x_test_df.csv"
    sample_df_artifact = make_test_artifact(Dataset)(output_path)
    X_test_component.python_func(dataset=sample_df_artifact)

    return sample_df_artifact


@component()
def y_test_component(dataset: Output[Dataset]):

    df = pd.read_csv("tests/data/y_test.csv")
    os.makedirs("tmp", exist_ok=True)
    dataset.path = "tmp/y_test_df.csv"
    df.to_csv(dataset.path, index=False)

    return

@pytest.fixture
def y_test_df():

    os.makedirs("tmp", exist_ok=True)
    output_path = "tmp/local_y_test_df.csv"
    sample_df_artifact = make_test_artifact(Dataset)(output_path)
    y_test_component.python_func(dataset=sample_df_artifact)

    return sample_df_artifact