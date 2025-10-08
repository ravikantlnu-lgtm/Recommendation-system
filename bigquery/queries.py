import os

# Determine which configuration to use
env = os.getenv("ENV", "dev")  # Default to 'dev' if ENV is not set

if env == "prod":
    import config_prod as config
else:
    import config_dev as config
    
CONSOLIDATED_PROJECTS_VIEW = f"""
-- Fetch all projects from the primary_project_leads 
with project_candidates as (
       SELECT
       primary_project_id,
       mg.project_id as candidate_project_id, 
       mg.project_source as candidate_source, 
       mg.sourceFileCreationTime as candidate_creation_time
       FROM
       `{config.PROJECT_ID}.{config.BIGQUERY_DATASET}.{config.PRIMARY_PROJECT_LEAD_TABLE}`,
       UNNEST(matched_group) AS mg
),
-- Cast and rename Dodge columns to mapped ConstructConnect columns
dodge_columns_mapped as (
       SELECT 
       DRNumber, 
       ProjectTitle as Title, 
       PrimaryStage as Stage, 
       ProjectURL as URL, 
       Valuation as Valuation_Value, 
       OwnershipType as Parameters_Parameter_Ownership, 
       CAST(BidDate as STRING) as Parameters_Parameter_BidDate, # Cast to string 
       BidTime as Parameters_Parameter_BidTime, 
       TypeOfWork as Parameters_Parameter_WorkType, 
       null as Parameters_Parameter_Structures,
       CASE
              WHEN LOWER(PlanAvailable) = 'yes' THEN TRUE
              WHEN LOWER(PlanAvailable) = 'no' THEN FALSE
              ELSE FALSE    
       END AS DocumentAvailability_Plans, # Cast to boolean 
       CASE
              WHEN LOWER(SpecAvailable) = 'yes' THEN TRUE
              WHEN LOWER(SpecAvailable) = 'no' THEN FALSE
              ELSE FALSE    
       END AS DocumentAvailability_Specs, # Cast to boolean 
       PrimaryProjectType as ParentCategories_PrimaryCategoryName, 
       [STRUCT(MarketSegment AS Name, STRUCT(CAST(NULL AS ARRAY<STRING>) AS SubCategory) AS SubCategories)] AS ParentCategories_ParentCategory, # Cast to Array<Struct>
       [STRUCT("Project" AS ProjectAddressType, 
              Address as AddressLine1, 
              "" as AddressLine2, 
              City,
              Country as CountryRegion, 
              County, 
              CAST(Lat as NUMERIC) as Latitude, 
              CAST(Long as NUMERIC) as Longitude, 
              State as StateProvince, 
              Zip as ZipPostalCode)] AS Addresses_Address, # Cast to Array<Struct>
              IF(FeaturesInfo IS NOT NULL, [STRUCT('Detail' as DetailType, FeaturesInfo as Detail)], []) as Details_Detail,
       sourceFileCreationTime, 
       FROM `{config.PROJECT_ID}.{config.BIGQUERY_DATASET}.{config.DODGE_FEED_TABLE}`
)

-- Select project data from ConstructConnect 
SELECT pc.primary_project_id,
       pc.candidate_source, 
       ProjectID,
       Title, 
       Stage, 
       URL, 
       Valuation_Value,
       Parameters_Parameter_Ownership,
       Parameters_Parameter_BidDate,   
       Parameters_Parameter_BidTime, 
       Parameters_Parameter_WorkType,
       Parameters_Parameter_Structures,
       DocumentAvailability_Plans,  
       DocumentAvailability_Specs, 
       DocumentAvailability_Addenda,
       ParentCategories_PrimaryCategoryName, 
       ParentCategories_ParentCategory, 
       Addresses_Address, 
       Details_Detail_Scope, 
       Details_Detail_Notes, 
       Details_Detail,
       Materials_Material, 
       RSMeansMaterialDivisions_Division_Metals,
       RSMeansMaterialDivisions_Division_ThermalandMoistureProtection,
       RSMeansMaterialDivisions_Division_Openings,
       RSMeansMaterialDivisions_Division_Finishes,
       RSMeansMaterialDivisions_Division_Masonry, 
       sourceFileCreationTime
FROM project_candidates pc
INNER JOIN `{config.PROJECT_ID}.{config.BIGQUERY_DATASET}.{config.CONSTRUCT_CONNECT_FEED_TABLE}` cc
       ON pc.candidate_source = 'construct_connect' 
       AND pc.candidate_project_id = cc.ProjectID 
       AND pc.candidate_creation_time = cc.sourceFileCreationTime

UNION ALL # Combine results from both sources

-- Select project data from Dodge 
SELECT pc.primary_project_id,
       pc.candidate_source, 
       DRNumber as ProjectID,
       Title, 
       Stage, 
       URL, 
       Valuation_Value,
       Parameters_Parameter_Ownership,
       Parameters_Parameter_BidDate,   
       null as Parameters_Parameter_BidTime, 
       Parameters_Parameter_WorkType,
       Parameters_Parameter_Structures,
       DocumentAvailability_Plans,  
       DocumentAvailability_Specs, 
       null as DocumentAvailability_Addenda,
       ParentCategories_PrimaryCategoryName, 
       ParentCategories_ParentCategory, 
       Addresses_Address, 
       null as Details_Detail_Scope, 
       null as Details_Detail_Notes, 
       Details_Detail,
       null as Materials_Material, 
       null as RSMeansMaterialDivisions_Division_Metals,
       null as RSMeansMaterialDivisions_Division_ThermalandMoistureProtection,
       null as RSMeansMaterialDivisions_Division_Openings,
       null as RSMeansMaterialDivisions_Division_Finishes,
       null as RSMeansMaterialDivisions_Division_Masonry, 
       sourceFileCreationTime
FROM project_candidates pc
INNER JOIN dodge_columns_mapped dodge
       ON pc.candidate_source = 'dodge' 
       AND pc.candidate_project_id = dodge.DRNumber 
       AND pc.candidate_creation_time = dodge.sourceFileCreationTime
""" 

COALESCED_PROJECT_VIEW_DYNAMIC_SQL = f""" 
-- Declare variables for dynamic SQL
DECLARE coalesce_ranking_cols STRING;
DECLARE ranking_cols ARRAY<STRING>;
DECLARE view_sql STRING; 

-- Fetch the ranking columns from the ranking_columns table
EXECUTE IMMEDIATE "SELECT ARRAY_AGG(name) FROM `{config.PROJECT_ID}.{config.BIGQUERY_DATASET}.{config.RANKING_COLUMNS_TABLE}`" INTO ranking_cols; 

-- Construct the COALESCE statement for each ranking column
SET coalesce_ranking_cols = (
  SELECT
    STRING_AGG(
      FORMAT('''COALESCE(
              IF(TO_JSON_STRING(cc.`%s`) IN ('""', '[]', '{{}}'), NULL, cc.`%s`),
              dd.`%s`
          ) AS `%s`''', col, col, col, col)
    )
  FROM
    UNNEST(ranking_cols) AS col
  WHERE
    col != 'ProjectID'
);

-- Construct the final SQL view statement
SET view_sql = FORMAT('''
       WITH ranked_projects AS (
       SELECT
              *,
              ROW_NUMBER() OVER (
              PARTITION BY primary_project_id, candidate_source
              ORDER BY sourceFileCreationTime DESC
              ) AS rn
       FROM `{config.PROJECT_ID}.{config.BIGQUERY_DATASET}.{config.CONSOLIDATED_PRIMARY_PROJECT_LEAD_VIEW}` pc
       WHERE
              candidate_source IN ('construct_connect', 'dodge')
       ),

       cc_data AS (
       SELECT * FROM ranked_projects WHERE candidate_source = 'construct_connect' AND rn = 1
       ),

       dodge_data AS (
       SELECT * FROM ranked_projects WHERE candidate_source = 'dodge' AND rn = 1
       )

       SELECT COALESCE(cc.primary_project_id, dd.primary_project_id) AS ProjectID,
              %s
       FROM cc_data AS cc FULL OUTER JOIN dodge_data AS dd
       ON cc.primary_project_id = dd.primary_project_id
''', coalesce_ranking_cols);

select view_sql;
""" 
