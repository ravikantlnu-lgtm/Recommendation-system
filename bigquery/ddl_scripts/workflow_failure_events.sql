CREATE TABLE IF NOT EXISTS `proj-sales-recommender-dev.sales_recommender_dev.workflow_failure_events`
(
  workflow_name STRING,
  failure_point STRING,
  error_type STRING,
  error_message STRING,
  input_data STRING,
  upload_timestamp DATETIME
);