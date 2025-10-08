from functools import lru_cache
from io import BytesIO, StringIO
from typing import Dict, List, Optional

from config import get_settings
from google.cloud import bigquery
from google.cloud.bigquery import Row, Table

settings = get_settings()


@lru_cache
def get_bigquery_client(project_id: str) -> bigquery.Client:
    """
    Function to get the BigQuery client object if it's cached and creates a new client if not
    """
    return bigquery.Client(project=project_id)


class BigQueryManager:
    def __init__(self, dataset_id: str, project_id: str = settings.PROJECT_ID):
        self._client = get_bigquery_client(project_id)
        self._dataset_id = dataset_id

    def create_table(self, table_id: str, schema: List[bigquery.SchemaField]) -> Table:
        table_ref = bigquery.DatasetReference(self._client.project, self._dataset_id).table(table_id)
        table = bigquery.Table(table_ref, schema=schema)
        table = self._client.create_table(table)
        return table

    def insert_rows(self, table_id: str, rows: List[Dict]) -> None:
        table_ref = bigquery.DatasetReference(self._client.project, self._dataset_id).table(table_id)
        errors = self._client.insert_rows_json(table_ref, rows)
        if errors:
            raise RuntimeError(f"Failed to insert rows: {errors}")

    def load_jsonl_file(self, table_id: str, file_content: StringIO) -> None:
        """
        Load a JSON newline-delimited content into a BigQuery table.

        :param table_id: The ID of the table to load data into.
        :param file_content: The JSONL content as a StringIO object.
        """

        try:
            table_ref = bigquery.DatasetReference(self._client.project, self._dataset_id).table(table_id)
            job_config = bigquery.LoadJobConfig(
                source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON
            )
            schema = self._client.get_table(table_ref).schema

            job_config = bigquery.LoadJobConfig(
                source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
                schema=schema,
            )
            load_job = self._client.load_table_from_file(
                file_content, table_ref, job_config=job_config
            )
            load_job.result()  # Wait for the job to complete.
            if load_job.errors:
                raise RuntimeError(f"Failed to load JSONL content: {load_job.errors}")
            # print(f"Loaded {load_job.output_rows} rows into {table_id}.")
        except Exception as e:
            raise ValueError(f"Error loading data into BigQuery: {e}")

    def query_table(self, query: str, to_dataframe=False, job_config=None) -> List[Row]:
        query_job = self._client.query(query,job_config=job_config)
        if to_dataframe:
            return query_job.to_dataframe()
        else:
            results = query_job.result()
            return list(results)

    def update_table_schema(
        self, table_id: str, schema: List[bigquery.SchemaField]
    ) -> Table:
        table_ref = bigquery.DatasetReference(self._client.project, self._dataset_id).table(table_id)
        table = self._client.get_table(table_ref)
        table.schema = schema
        table = self._client.update_table(table, ["schema"])
        return table

    def delete_table(self, table_id: str) -> None:
        table_ref = bigquery.DatasetReference(self._client.project, self._dataset_id).table(table_id)
        self._client.delete_table(table_ref)

    def delete_rows(self, table_id: str, condition: str) -> None:
        query = f"DELETE FROM `{self._dataset_id}.{table_id}` WHERE {condition}"
        query_job = self._client.query(query)
        query_job.result()  # Wait for the job to complete

    def load_from_dataframe(
        self, table_id: str, dataframe, job_config: Optional[bigquery.LoadJobConfig] = None
    ) -> bigquery.LoadJob:
        table_ref = bigquery.DatasetReference(self._client.project, self._dataset_id).table(table_id)
        job = self._client.load_table_from_dataframe(
            dataframe, table_ref, job_config=job_config
        )
        job.result() # Wait for the job to complete
        if job.error_result:
            raise RuntimeError(f"Failed to load data: {job.error_result}")
        
        return job

    def truncate_table(self, table_id: str) -> None:
        query = f"TRUNCATE TABLE `{self._dataset_id}.{table_id}`"
        query_job = self._client.query(query)
        query_job.result()

    def get_schema(self, table_id: str):
        table_ref = bigquery.DatasetReference(self._client.project, self._dataset_id).table(table_id)
        table = self._client.get_table(table_ref)
        schema = table.schema 
        return schema
