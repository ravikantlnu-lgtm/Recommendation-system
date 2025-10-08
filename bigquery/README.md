# BigQuery Folder

This folder contains scripts and configuration files for setting up and managing BigQuery tables and views for the FBM Sales Recommender project.

## Folder Structure

```
bigquery/
├── build_tables.py             # Python script to create datasets, tables, and views
├── config_dev.py               # Configuration for the development environment
├── config_prod.py              # Configuration for the production environment
├── dev.sh                      # Shell script to set up the development environment
├── prod.sh                     # Shell script to set up the production environment
├── requirements.txt            # Python dependencies
├── tables_metadata_info.json   # Metadata for tables (partitioning, clustering, keys, defaults)
├── ddl_scripts/                # Directory for SQL DDL table creation scripts
│   ├── assigned_search.sql
│   ├── construct_connect_feed.sql
│   ├── hist_construct_connect_feed_log.sql
│   ├── project_relevance.sql
│   ├── ranking_columns.sql
│   ├── relevant_categories.sql
│   ├── relevant_materials.sql
│   ├── searches_staging.sql
│   ├── searches_territories_map_staging.sql
│   └── ...                     # Other DDL scripts
├── schemas/                    # Directory for JSON table schema definitions
│   └── ...                     # Schema files
└── static_data_files/          # Directory for static data CSV files
    └── ...                     # CSV files
```

## Files and Directories

*   **`build_tables.py`**: This Python script is responsible for:
    *   Creating the BigQuery dataset if it doesn't exist.
    *   Creating tables based on schema definitions (likely found in the `schemas/` directory or defined within the script).
    *   Creating views based on SQL queries.
    It uses configurations from `config_dev.py` or `config_prod.py` based on the `ENV` environment variable.

*   **`config_dev.py`** and **`config_prod.py`**: These files define environment-specific configurations:
    *   `PROJECT_ID`: Google Cloud Project ID.
    *   `REGION`: Google Cloud Region.
    *   `BIGQUERY_DATASET`: Name of the BigQuery dataset.
    *   Table names for various entities like `CONSTRUCT_CONNECT_FEED_TABLE`, `PROJECT_RELEVANCE_TABLE`, etc.

*   **`dev.sh`** and **`prod.sh`**: These shell scripts automate the setup for development and production environments, respectively. They typically perform the following actions:
    *   Set the `ENV` environment variable (`dev` or `prod`).
    *   Install Python dependencies from `requirements.txt`.
    *   Execute `build_tables.py` to create the necessary BigQuery schema.
    *   Copy CSV files from `static_data_files/` to a GCS bucket.
    *   Load data from the CSV files in the GCS bucket into the corresponding BigQuery tables using `bq load` commands.

*   **`requirements.txt`**: Specifies the Python packages required for the scripts in this folder. The primary dependency is `google-cloud-bigquery`.

*   **`tables_metadata_info.json`**: Contains JSON-formatted metadata about the BigQuery tables. This includes:
    *   `partition_cluster_info`: Information about table partitioning and clustering.
    *   `pk_fk_info`: Definitions of primary and foreign keys.
    *   `default_values_info`: Default values for table columns.

*   **`ddl_scripts/`**: This directory stores SQL DDL scripts. Each `.sql` file likely contains the `CREATE TABLE` statement for a specific table. These scripts are probably used by `build_tables.py`.

*   **`schemas/`**: This directory is intended to hold JSON files that define the schema for each BigQuery table. These schema files are likely referenced by `build_tables.py` when creating tables.

*   **`static_data_files/`**: This directory contains CSV files with static or seed data. The `dev.sh` and `prod.sh` scripts upload these files to Google Cloud Storage and then load them into the appropriate BigQuery tables (e.g., `ranking_columns`, `relevant_categories`, `relevant_materials`).

## Setup and Usage

1.  **Set Environment Variable**:
    Before running any setup script, ensure the `ENV` environment variable is set to either `dev` or `prod` to specify the target environment.
    ```bash
    export ENV=dev  # For development
    # or
    export ENV=prod # For production
    ```

2.  **Install Dependencies**:
    Navigate to the `bigquery/` directory and install the required Python packages:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Run Setup Script**:
    Execute the appropriate shell script for your environment:
    *   For development:
        ```bash
        ./dev.sh
        ```
    *   For production:
        ```bash
        ./prod.sh
        ```
    These scripts will:
    *   Create the BigQuery dataset and tables.
    *   Upload static data to Google Cloud Storage.
    *   Load the static data into the BigQuery tables.

## Key Tables Managed

This folder manages the schema and initial data for several key BigQuery tables, including but not limited to:

*   `construct_connect_feed`: Stores data from the ConstructConnect feed.
*   `project_relevance`: Stores relevance information for projects.
*   `ranking_columns`: Defines columns used for ranking.
*   `relevant_categories`: Lists categories considered relevant.
*   `relevant_materials`: Lists materials considered relevant.
*   `searches`: Stores search queries.
*   `territories`: Stores territory information.
*   `searches_territories_map`: Maps searches to territories.
*   Staging tables for `searches`, `territories`, and `searches_territories_map`.
*   `assigned_search`: Tracks projects assigned to searches.
*   `workflow_failure_events`: Logs failures in workflows.
*   `hist_construct_connect_feed_log`: Log for historical ConstructConnect feed data.
*   `latest_tuned_llm_model`: Information about the latest tuned LLM model.
*   `tuned_model_performances`: Performance metrics for tuned models.

Refer to `config_dev.py`, `config_prod.py`, and `tables_metadata_info.json` for a complete list and detailed descriptions of tables and their attributes.
