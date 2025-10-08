# Python Scripts

This directory contains various Python scripts for interacting with and managing the FBM Sales Recommender system. These scripts are typically used for ad-hoc tasks, batch processing, and triggering workflows.

## Scripts

Below is a list of the Python scripts in this directory, along with a brief description of their purpose:

- **`sync_project_relevance_crm.py`**: This script synchronizes project relevance data, including leads and opportunities, between BigQuery and Dynamics CRM. It identifies new or updated relevance scores in BigQuery and pushes these updates to CRM. It can also create new leads or update existing ones based on the relevance information.
- **`trigger_CF_hist_data.py`**: This script is designed to trigger the `hist_xml_load` Cloud Function for a batch of historical XML files. It reads a list of files (presumably from Google Cloud Storage), and invokes the Cloud Function for each file, likely in parallel, to process and load historical project data.
- **`trigger_backfill_projects.py`**: This script triggers the `backfill_projects` Cloud Function. This is used to initiate the backfilling process for projects, which involves fetching older project data and running it through the relevance and assignment pipeline.
- **`trigger_project_id_workflow.py`**: This script is used to trigger a specific workflow (likely a Google Cloud Workflow) for a given list of project IDs. It reads project IDs from a file and initiates the workflow for each. There is an accompanying `trigger_project_id_workflow_Readme.md` that might contain more specific instructions for this script.

## General Usage

Before running any script, ensure that:
1. You have the necessary permissions and authentication set up for Google Cloud Platform services (BigQuery, Cloud Functions, Cloud Storage, Workflows) and Dynamics CRM.
2. The environment variables in the `.env` file (if used by the script) are correctly configured for your target environment (dev, prod).
3. You understand the purpose of the script and any potential impact it might have on data in BigQuery or CRM.

Refer to the individual script files for more detailed comments or specific command-line arguments they might accept. The `trigger_project_id_workflow_Readme.md` should be consulted for specific instructions on using `trigger_project_id_workflow.py`.
