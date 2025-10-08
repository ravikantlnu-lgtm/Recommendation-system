CREATE TABLE IF NOT EXISTS `proj-sales-recommender-dev.sales_recommender_dev.project_relevance`
(
  project_id INT64 REFERENCES sales_recommender_dev.construct_connect_feed(ProjectID) NOT ENFORCED OPTIONS (description="Unique identifier for the project"),
  relevance STRING OPTIONS(description="relevance classification"),
  reasoning STRING OPTIONS(description="reasoning for relevance classification"),
  search_id STRING OPTIONS(description="Search ID"),
  territory_id STRING OPTIONS(description="Territory ID"),
  time_created DATETIME OPTIONS(description="Time Created from Construct_connect_feed"),
  source STRING OPTIONS(description="lead source (cmd,other,etc)"),
  modified_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP() OPTIONS(description="Timestamp when the record was last modified"),
  distance FLOAT64
)
PARTITION BY DATE(time_created)
CLUSTER BY project_id;