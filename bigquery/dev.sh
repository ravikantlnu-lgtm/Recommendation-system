#!/bin/bash
# Set the ENV environment variable to dev
export ENV=dev
BUCKET_NAME="sales-rec-staging"
PROJECT_ID="proj-sales-recommender-dev"
DATASET_ID="sales_recommender_dev"

RANKING_TABLE="ranking_columns"
RELEVANT_CATEGORIES_TABLE="relevant_categories"
RELEVANT_MATERIALS_TABLE="relevant_materials"


# Install required Python packages
pip install -r requirements.txt

# Run the build_tables.py script
python build_tables.py


gsutil cp ./static_data_files/*.csv gs://${BUCKET_NAME}/static-data/


bq load --project_id=${PROJECT_ID} \
  --source_format=CSV \
  --skip_leading_rows=1 \
  --replace \
  ${DATASET_ID}.${RANKING_TABLE} \
  gs://${BUCKET_NAME}/static-data/${RANKING_TABLE}.csv \
  name:STRING

bq load --project_id=${PROJECT_ID} \
  --source_format=CSV \
  --skip_leading_rows=1 \
  --replace \
  ${DATASET_ID}.${RELEVANT_CATEGORIES_TABLE} \
  gs://${BUCKET_NAME}/static-data/${RELEVANT_CATEGORIES_TABLE}.csv \
  category_type:STRING,parent_category:STRING,value:STRING,source:STRING


bq load --project_id=${PROJECT_ID} \
  --source_format=CSV \
  --skip_leading_rows=1 \
  --replace \
  ${DATASET_ID}.${RELEVANT_MATERIALS_TABLE} \
  gs://${BUCKET_NAME}/static-data/${RELEVANT_MATERIALS_TABLE}.csv \
  division:STRING,material:STRING,code:INTEGER,source:STRING
