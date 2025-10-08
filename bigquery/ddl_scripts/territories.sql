CREATE TABLE IF NOT EXISTS `proj-sales-recommender-dev.sales_recommender_dev.territories`
(
  id STRING NOT NULL OPTIONS(description="Territory ID (UUID)"),
  name STRING OPTIONS(description="Territory name"),
  latitude FLOAT64 OPTIONS(description="Territory lattitude"),
  longitude FLOAT64 OPTIONS(description="Territory longitude"),
  upsert_time DATETIME OPTIONS(description="Time when search was upserted"),
  PRIMARY KEY (id) NOT ENFORCED
)
PARTITION BY DATE(upsert_time)
CLUSTER BY id, name;