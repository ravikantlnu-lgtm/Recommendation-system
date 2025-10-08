CREATE TABLE IF NOT EXISTS proj-sales-recommender-dev.sales_recommender_dev.ranking_columns (
    name STRING OPTIONS(description="name of construct_connect_feed column"),
)
CLUSTER BY name;