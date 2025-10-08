import json
import mimetypes
import os
import re
from functools import lru_cache
from typing import BinaryIO, Dict, Optional, Union

from config import get_settings
from google.cloud import storage
from google.cloud.storage import Blob
from io import BytesIO

settings = get_settings()


@lru_cache
def get_cloud_storage_client() -> storage.Client:
    """
    Function to get the Cloud Storage client object if it's cached and creates a new client if not
    """
    return storage.Client(project=settings.PROJECT_ID)


class GCSFileManager:
    def __init__(self, bucket: str):
        self._client = get_cloud_storage_client()
        self._bucket: storage.Bucket = self._client.bucket(bucket)

    @staticmethod
    def parse_gcs_uri(gcs_uri: str):
        """
        Parse GCS URI and return the bucket and file path.
        Example URI: 'gs://source-bucket-name/folder/subfolder/file.json'
        Returns: (bucket_name, file_path)
        """
        pattern = r"^gs://([^/]+)/(.+)$"
        match = re.match(pattern, gcs_uri)
        if not match:
            raise ValueError(f"Invalid GCS URI format: {gcs_uri}")
        bucket_name = match.group(1)
        file_path = match.group(2)
        return bucket_name, file_path

    def _list_files(self, directory_path: str) -> list[Blob]:
        blobs = self._bucket.list_blobs(prefix=directory_path)
        return list(blobs)

    def upload_file(self, path: str, file: BinaryIO, file_name: str) -> None:
        blob = self._bucket.blob(f"{path}/{file_name}")
        if blob.exists():
            # TODO: what should happen if a file already exists?
            return None
        blob.upload_from_file(file)

    def download_file(
        self, file_path: str, file_format: str = "bytes"
    ) -> Optional[Union[bytes, dict, list]]:
        blob = self._bucket.blob(file_path)
        if not blob.exists():
            # TODO: what should happen if a file doesn't exist?
            return None
        if file_format == "json":
            return json.loads(blob.download_as_text())
        else:
            return blob.download_as_bytes()

    def copy_file(
        self,
        source_gcs_uri: str,
        destination_bucket_name: str,
        destination_folder_name: str,
        print_destination: bool = True,
    ):
        """
        Copy a file from a source GCS URI to a destination bucket and folder.
        :param source_gcs_uri: GCS URI of the source file
        :param destination_bucket_name: Name of the destination GCS bucket
        :param destination_folder_name: Folder in the destination bucket
        """
        # Parse the source GCS URI
        source_bucket_name, source_file_path = self.parse_gcs_uri(source_gcs_uri)

        # Get the source bucket and blob
        source_bucket = self._client.bucket(source_bucket_name)
        source_blob = source_bucket.blob(source_file_path)

        if not source_blob.exists():
            raise FileNotFoundError(f"Source file {source_gcs_uri} does not exist.")
            return False

        # Build the destination file path, placing the file inside the destination folder
        file_name = os.path.basename(source_file_path)
        destination_file_path = os.path.join(destination_folder_name, file_name)

        # Get the destination bucket
        destination_bucket = self._client.bucket(destination_bucket_name)

        # Copy the file from source to destination
        # Copy the blob from the source bucket to the destination bucket and folder
        source_bucket.copy_blob(source_blob, destination_bucket, destination_file_path)
        # source_blob.copy_to_bucket(destination_bucket, new_name=destination_file_path)

        # Construct the new GCS URI
        new_gcs_uri = f"gs://{destination_bucket_name}/{destination_file_path}"

        if print_destination:
            print(f"File copied from {source_gcs_uri} to {new_gcs_uri}")

        return new_gcs_uri

    def download_by_filename(
        self, file_path: str, destination_file_name: str
    ) -> Optional[bytes]:
        blob = self._bucket.blob(file_path)
        if not blob.exists():
            # TODO: what should happen if a file doesnt exist?
            return None
        return blob.download_to_filename(destination_file_name)

    def delete_file(self, file_path: str) -> None:
        blob = self._bucket.blob(file_path)
        if not blob.exists():
            # TODO: what should happen if a file doesnt exist?
            return None
        blob.delete()

    def delete_files_from_directory(self, directory_path: str) -> None:
        blobs = self._list_files(directory_path)
        if len(blobs) == 0:
            # TODO: what should happen if the directory is empty?
            return None
        self._bucket.delete_blobs(blobs)

    def get_project_id(self) -> str:
        try:
            return self._client.project
        except Exception as e:
            print(f"Error retrieving project ID: {e}")
            return None

    def get_file_bytes(self, file_path: str) -> Optional[bytes]:
        blob = self._bucket.blob(file_path)
        if not blob.exists():
            # TODO: what should happen if file does not exist?
            return None
        file_bytes = blob.download_as_bytes()
        return file_bytes

    def upload_data(
        self, file_path: str, data: Union[BinaryIO, Dict], return_uri: bool = True
    ) -> None:
        """Uploads data to a GCS bucket.

        Args:
            file_path: The path within the bucket to store the file.
            data: The data to be uploaded.
        """

        # Create a blob in the bucket
        blob = self._bucket.blob(file_path)

        # Extract the file name from the file path
        file_name = os.path.basename(file_path)

        # Infer the data format from the file extension
        data_format = mimetypes.guess_type(file_name)[0]

        if isinstance(data, dict):
            # If data is a dictionary, convert it to a JSON string
            data = json.dumps(data)

        # Upload data as a string
        blob.upload_from_string(data, content_type=data_format)

        if return_uri:
            return f"gs://{blob.bucket.name}/{blob.name}"

    def upload_file(
        self, file_path: str, file: BytesIO, content_type: str = None, return_uri: bool = True
    ) -> storage.Blob:
        """
        Uploads a file to a GCS bucket.

        Args:
            file_path (str): The path within the bucket to store the file.
            file (BytesIO): The file to be uploaded.
            return_uri (bool, optional): Whether to return the GCS URI of the uploaded file. Defaults to True.
            content_type (str, optional): The MIME type of the file. Defaults to None.

        Returns:
            storage.Blob: The Blob object of the uploaded file.
        """
        blob = self._bucket.blob(file_path)
        blob.upload_from_file(file, content_type=content_type)
        return blob
