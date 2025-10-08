CREATE TABLE IF NOT EXISTS proj-sales-recommender-dev.sales_recommender_dev.searches_territories_map (
    territory_id STRING NOT NULL OPTIONS(description="Territory ID (UUID)"),
    search_id STRING NOT NULL OPTIONS(description="Search ID (UUID)")
)
CLUSTER BY territory_id, search_id
;