CREATE TABLE IF NOT EXISTS proj-sales-recommender-dev.sales_recommender_dev.searches (
    id STRING NOT NULL OPTIONS(description="Search ID (UUID)"),
    name STRING OPTIONS(description="Search name"),
    category STRING OPTIONS(description="Search category"),
    boolean STRING OPTIONS(description="Boolean search values"),
    upsert_time DATETIME OPTIONS(description="Time when search was upserted"),
    PRIMARY KEY (id) NOT ENFORCED
)
PARTITION BY DATE(upsert_time)
CLUSTER BY id,name,category;
