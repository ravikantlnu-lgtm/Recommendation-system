CREATE TABLE IF NOT EXISTS  `proj-sales-recommender-dev.sales_recommender_dev.relevant_categories`
(
  category_type STRING OPTIONS(description="sub category"),
  parent_category STRING OPTIONS(description="Parent category"),
  value STRING OPTIONS(description="sub category value"),
  source STRING OPTIONS(description="data source")
)
CLUSTER BY parent_category, category_type ,value;