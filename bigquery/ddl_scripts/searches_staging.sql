CREATE TABLE IF NOT EXISTS proj-sales-recommender-dev.sales_recommender_dev.searches_staging (
    id STRING NOT NULL OPTIONS(description="Search ID (UUID)"),
    name STRING OPTIONS(description="Search name"),
    category STRING OPTIONS(description="Search category"),
    boolean STRING OPTIONS(description="Boolean search values"),
    upsert_time DATETIME OPTIONS(description="Time when search was upserted"),
)
;
