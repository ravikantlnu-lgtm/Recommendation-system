CREATE TABLE IF NOT EXISTS proj-sales-recommender-dev.sales_recommender_dev.assigned_search (
    project_id INT64 REFERENCES sales_recommender_dev.construct_connect_feed(ProjectId) NOT ENFORCED OPTIONS(description="ProjectId from construct_connect_feed"),
    search_id STRING REFERENCES sales_recommender_dev.searches(id) NOT ENFORCED OPTIONS (description="Search ID from CRM searches (UUID)"),
    territory_id STRING REFERENCES sales_recommender_dev.territories(id) NOT ENFORCED OPTIONS (description="Territory ID from CRM territories (UUID)"),
    time_created DATETIME OPTIONS(description="Time Created from Construct_connect_feed"),
   
)
PARTITION BY DATE(time_created)
CLUSTER BY project_id, search_id, territory_id;