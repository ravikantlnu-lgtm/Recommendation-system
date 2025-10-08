CREATE TABLE IF NOT EXISTS `proj-sales-recommender-dev.sales_recommender_dev.relevant_materials`
(
  division STRING OPTIONS(description="Material division"),
  material STRING OPTIONS(description="Material name"),
  code INT64 OPTIONS(description="Material code"),
  source STRING OPTIONS(description="data source")
)
CLUSTER BY division, material, code;