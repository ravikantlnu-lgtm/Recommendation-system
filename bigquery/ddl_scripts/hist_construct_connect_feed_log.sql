CREATE TABLE IF NOT EXISTS  `proj-sales-recommender-dev.sales_recommender_dev.hist_construct_connect_feed_log`
(
  file_path STRING,
  num_rows INT64,
  status STRING,
  create_dttm TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);