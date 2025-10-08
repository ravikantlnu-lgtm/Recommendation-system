#!/bin/bash

# Define common variables
BASE_DIR="../CloudFunction"
DEPLOY_SCRIPT="python ./deploy_cloud_function.py"
# Set environment variable
echo "Environment: $ENVIRONMENT"

# Deploy functions
$DEPLOY_SCRIPT --function-name="send-relevent-project-to-queue" \
               --source-dir="$BASE_DIR" \
               --entry-point="send_projects_to_queue" \
               --main-cloud-function-file="send_relevent_project_to_queue.py" \
               --runtime="python312" \
               --env="ENV=${ENVIRONMENT}"

$DEPLOY_SCRIPT --function-name="search-territory-updates" \
               --source-dir="$BASE_DIR" \
               --entry-point="search_territory_updates" \
               --main-cloud-function-file="search_territory_updates.py" \
               --secrets="dynamics_cred=dynamics_cred:1" \
               --runtime="python312" \
               --env="ENV=${ENVIRONMENT}"

$DEPLOY_SCRIPT --function-name="process-hist-xml-files" \
               --source-dir="$BASE_DIR" \
               --entry-point="gcs_to_bq" \
               --main-cloud-function-file="hist_xml_load.py"\
               --memory="32GiB" \
               --cpu="8" \
               --env="ENV=${ENVIRONMENT}"
               
$DEPLOY_SCRIPT --function-name="process-xml-files" \
               --source-dir="$BASE_DIR" \
               --entry-point="gcs_to_bq" \
               --main-cloud-function-file="data_intake.py"\
               --memory="32GiB" \
               --cpu="8" \
               --env="ENV=${ENVIRONMENT}"


$DEPLOY_SCRIPT --function-name="assign-relevance" \
               --source-dir="$BASE_DIR" \
               --entry-point="assign_relevance" \
               --main-cloud-function-file="assign_relevance.py" \
               --concurrency=10 \
               --memory="12GiB" \
               --cpu="4" \
               --max-instances=1000 \
               --runtime="python312" \
               --env="ENV=${ENVIRONMENT}"


$DEPLOY_SCRIPT --function-name="split-large-xml-files" \
               --source-dir="$BASE_DIR" \
               --entry-point="split_xml" \
               --main-cloud-function-file="split_large_xml_files.py"\
               --memory="32GiB" \
               --cpu="8" \
                --secrets="default-service-account=default-service-account:1" \
                --runtime="python312" \
               --env="ENV=${ENVIRONMENT}"

$DEPLOY_SCRIPT --function-name="workflow-failure" \
               --source-dir="$BASE_DIR" \
               --entry-point="handle_workflow_failure" \
               --main-cloud-function-file="workflow_failure.py" \
               --runtime="python312" \
               --env="ENV=${ENVIRONMENT}"

$DEPLOY_SCRIPT --function-name="assign-project-to-search" \
               --source-dir="$BASE_DIR" \
               --entry-point="assign_project_search" \
               --main-cloud-function-file="assign_project_to_search.py" \
               --concurrency=10 \
               --memory="8GiB" \
               --cpu="4" \
               --max-instances=1000 \
               --runtime="python312" \
               --env="ENV=${ENVIRONMENT}"

$DEPLOY_SCRIPT --function-name="reroute-to-search-or-relevance-queue" \
               --source-dir="$BASE_DIR" \
               --entry-point="reroute_to_search_or_relevance_queue" \
               --main-cloud-function-file="reroute_to_search_or_relevance_queue.py" \
               --max-instances=1000 \
               --runtime="python312" \
               --env="ENV=${ENVIRONMENT}"

$DEPLOY_SCRIPT --function-name="trigger-batch-upsert-lead" \
               --source-dir="$BASE_DIR" \
               --entry-point="trigger_batch_upsert_lead" \
               --main-cloud-function-file="trigger_batch_upsert_lead_function.py" \
               --runtime="python312" \
               --env="ENV=${ENVIRONMENT}"

$DEPLOY_SCRIPT --function-name="batch-upsert-leads" \
               --source-dir="$BASE_DIR" \
               --entry-point="batch_upsert_leads" \
               --main-cloud-function-file="batch_upsert_leads.py" \
               --memory="8GiB" \
               --cpu="2" \
               --runtime="python312" \
               --env="ENV=${ENVIRONMENT}"

$DEPLOY_SCRIPT --function-name="backfill-projects" \
               --source-dir="$BASE_DIR" \
               --entry-point="backfill_projects" \
               --main-cloud-function-file="backfill_projects.py" \
               --memory="16GiB" \
               --cpu="4" \
               --runtime="python312" \
               --env="ENV=${ENVIRONMENT}"

$DEPLOY_SCRIPT --function-name="resolve-potential-duplicates" \
               --source-dir="$BASE_DIR" \
               --entry-point="resolve_potential_duplicates" \
               --main-cloud-function-file="resolve_potential_duplicates.py" \
               --runtime="python312" \
               --env="ENV=${ENVIRONMENT}"

$DEPLOY_SCRIPT --function-name="deduplicate-projects-batch" \
               --source-dir="$BASE_DIR" \
               --entry-point="deduplicate_projects_batch" \
               --main-cloud-function-file="deduplicate_projects_batch.py" \
               --env="ENV=${ENVIRONMENT}"

$DEPLOY_SCRIPT --function-name="unification" \
               --source-dir="$BASE_DIR" \
               --entry-point="unification" \
               --main-cloud-function-file="unification.py" \
               --runtime="python312" \
               --env="ENV=${ENVIRONMENT}"

$DEPLOY_SCRIPT --function-name="deduplicate-projects-batch" \
               --source-dir="$BASE_DIR" \
               --entry-point="deduplicate_projects_batch" \
               --main-cloud-function-file="deduplicate_projects_batch.py" \
               --runtime="python312" \
               --env="ENV=${ENVIRONMENT}"
