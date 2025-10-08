from collections import defaultdict
import uuid


class UnionFind:
    """Standard Union-Find data structure."""
    def __init__(self):
        self.parent = {}

    def find(self, x):
        if x not in self.parent:
            self.parent[x] = x
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, x, y):
        self.parent[self.find(x)] = self.find(y)

def get_uuid():
    """Generates a new UUID string."""
    return str(uuid.uuid4())

def normalize_project(project_dict):
    """
        Normalizes keys for project and potential_match_project dicts 
        into a consistent structure.
    """
    if "potential_match_id" in project_dict:
        return {
            "project_id": project_dict["potential_match_id"],
            "project_source": project_dict.get("potential_match_source"),
            "sourceFileCreationTime": project_dict.get("potential_match_sourceFileCreationTime"),
            "delta_record": project_dict.get("delta_record"),
            "existing_primary_project_id": project_dict.get("existing_primary_project_id"),
        }
    else:
        return {
            "project_id": project_dict["project_id"],
            "project_source": project_dict.get("project_source"),
            "sourceFileCreationTime": project_dict.get("sourceFileCreationTime"),
            "delta_record": project_dict.get("delta_record"),
            "existing_primary_project_id": project_dict.get("existing_primary_project_id"),
        }
    

COALESCED_PRIMARY_PROJECT_QUERY = """

       WITH ranked_projects AS (
       SELECT
              *,
              ROW_NUMBER() OVER (
              PARTITION BY primary_project_id, candidate_source
              ORDER BY sourceFileCreationTime DESC
              ) AS rn
       FROM `{consolidated_primary_project_table_path}` pc
       WHERE  batch_id = @batch_id 
              AND candidate_source IN ('construct_connect', 'dodge')
       ),

       cc_data AS (
       SELECT * FROM ranked_projects WHERE candidate_source = 'construct_connect' AND rn = 1
       ),

       dodge_data AS (
       SELECT * FROM ranked_projects WHERE candidate_source = 'dodge' AND rn = 1
       )

       SELECT COALESCE(cc.batch_id, dd.batch_id) batch_id,
              COALESCE(cc.primary_project_id, dd.primary_project_id) AS ProjectID,
              COALESCE(
              IF(TO_JSON_STRING(cc.`Details_Detail_Scope`) IN ('""', '[]', '{{}}'), NULL, cc.`Details_Detail_Scope`),
              dd.`Details_Detail_Scope`
          ) AS `Details_Detail_Scope`,COALESCE(
              IF(TO_JSON_STRING(cc.`RSMeansMaterialDivisions_Division_Masonry`) IN ('""', '[]', '{{}}'), NULL, cc.`RSMeansMaterialDivisions_Division_Masonry`),
              dd.`RSMeansMaterialDivisions_Division_Masonry`
          ) AS `RSMeansMaterialDivisions_Division_Masonry`,COALESCE(
              IF(TO_JSON_STRING(cc.`Parameters_Parameter_Structures`) IN ('""', '[]', '{{}}'), NULL, cc.`Parameters_Parameter_Structures`),
              dd.`Parameters_Parameter_Structures`
          ) AS `Parameters_Parameter_Structures`,COALESCE(
              IF(TO_JSON_STRING(cc.`DocumentAvailability_Plans`) IN ('""', '[]', '{{}}'), NULL, cc.`DocumentAvailability_Plans`),
              dd.`DocumentAvailability_Plans`
          ) AS `DocumentAvailability_Plans`,COALESCE(
              IF(TO_JSON_STRING(cc.`Materials_Material`) IN ('""', '[]', '{{}}'), NULL, cc.`Materials_Material`),
              dd.`Materials_Material`
          ) AS `Materials_Material`,COALESCE(
              IF(TO_JSON_STRING(cc.`RSMeansMaterialDivisions_Division_Finishes`) IN ('""', '[]', '{{}}'), NULL, cc.`RSMeansMaterialDivisions_Division_Finishes`),
              dd.`RSMeansMaterialDivisions_Division_Finishes`
          ) AS `RSMeansMaterialDivisions_Division_Finishes`,COALESCE(
              IF(TO_JSON_STRING(cc.`Addresses_Address`) IN ('""', '[]', '{{}}'), NULL, cc.`Addresses_Address`),
              dd.`Addresses_Address`
          ) AS `Addresses_Address`,COALESCE(
              IF(TO_JSON_STRING(cc.`Stage`) IN ('""', '[]', '{{}}'), NULL, cc.`Stage`),
              dd.`Stage`
          ) AS `Stage`,COALESCE(
              IF(TO_JSON_STRING(cc.`Parameters_Parameter_WorkType`) IN ('""', '[]', '{{}}'), NULL, cc.`Parameters_Parameter_WorkType`),
              dd.`Parameters_Parameter_WorkType`
          ) AS `Parameters_Parameter_WorkType`,COALESCE(
              IF(TO_JSON_STRING(cc.`Details_Detail_Notes`) IN ('""', '[]', '{{}}'), NULL, cc.`Details_Detail_Notes`),
              dd.`Details_Detail_Notes`
          ) AS `Details_Detail_Notes`,COALESCE(
              IF(TO_JSON_STRING(cc.`Parameters_Parameter_Ownership`) IN ('""', '[]', '{{}}'), NULL, cc.`Parameters_Parameter_Ownership`),
              dd.`Parameters_Parameter_Ownership`
          ) AS `Parameters_Parameter_Ownership`,COALESCE(
              IF(TO_JSON_STRING(cc.`DocumentAvailability_Specs`) IN ('""', '[]', '{{}}'), NULL, cc.`DocumentAvailability_Specs`),
              dd.`DocumentAvailability_Specs`
          ) AS `DocumentAvailability_Specs`,COALESCE(
              IF(TO_JSON_STRING(cc.`Details_Detail`) IN ('""', '[]', '{{}}'), NULL, cc.`Details_Detail`),
              dd.`Details_Detail`
          ) AS `Details_Detail`,COALESCE(
              IF(TO_JSON_STRING(cc.`ParentCategories_ParentCategory`) IN ('""', '[]', '{{}}'), NULL, cc.`ParentCategories_ParentCategory`),
              dd.`ParentCategories_ParentCategory`
          ) AS `ParentCategories_ParentCategory`,COALESCE(
              IF(TO_JSON_STRING(cc.`RSMeansMaterialDivisions_Division_Openings`) IN ('""', '[]', '{{}}'), NULL, cc.`RSMeansMaterialDivisions_Division_Openings`),
              dd.`RSMeansMaterialDivisions_Division_Openings`
          ) AS `RSMeansMaterialDivisions_Division_Openings`,COALESCE(
              IF(TO_JSON_STRING(cc.`RSMeansMaterialDivisions_Division_ThermalandMoistureProtection`) IN ('""', '[]', '{{}}'), NULL, cc.`RSMeansMaterialDivisions_Division_ThermalandMoistureProtection`),
              dd.`RSMeansMaterialDivisions_Division_ThermalandMoistureProtection`
          ) AS `RSMeansMaterialDivisions_Division_ThermalandMoistureProtection`,COALESCE(
              IF(TO_JSON_STRING(cc.`ParentCategories_PrimaryCategoryName`) IN ('""', '[]', '{{}}'), NULL, cc.`ParentCategories_PrimaryCategoryName`),
              dd.`ParentCategories_PrimaryCategoryName`
          ) AS `ParentCategories_PrimaryCategoryName`,COALESCE(
              IF(TO_JSON_STRING(cc.`RSMeansMaterialDivisions_Division_Metals`) IN ('""', '[]', '{{}}'), NULL, cc.`RSMeansMaterialDivisions_Division_Metals`),
              dd.`RSMeansMaterialDivisions_Division_Metals`
          ) AS `RSMeansMaterialDivisions_Division_Metals`,COALESCE(
              IF(TO_JSON_STRING(cc.`Valuation_Value`) IN ('""', '[]', '{{}}'), NULL, cc.`Valuation_Value`),
              dd.`Valuation_Value`
          ) AS `Valuation_Value`,COALESCE(
              IF(TO_JSON_STRING(cc.`DocumentAvailability_Addenda`) IN ('""', '[]', '{{}}'), NULL, cc.`DocumentAvailability_Addenda`),
              dd.`DocumentAvailability_Addenda`
          ) AS `DocumentAvailability_Addenda`,COALESCE(
              IF(TO_JSON_STRING(cc.`Title`) IN ('""', '[]', '{{}}'), NULL, cc.`Title`),
              dd.`Title`
          ) AS `Title`,
        COALESCE(cc.Parameters_Parameter_BidDate , dd.Parameters_Parameter_BidDate) as Parameters_Parameter_BidDate,
        COALESCE(cc.Parameters_Parameter_CommenceDate , dd.Parameters_Parameter_CommenceDate ) Parameters_Parameter_CommenceDate,
        DATETIME(COALESCE(cc.sourceFileCreationTime , dd.sourceFileCreationTime )) sourceFileCreationTime,
        COALESCE(cc.URL , dd.URL )  URL,
        COALESCE(cc.Parameters_Parameter_FloorArea , dd.Parameters_Parameter_FloorArea )  Parameters_Parameter_FloorArea,
        COALESCE(cc.GC_company , dd.GC_company )  GC_company,
        COALESCE(cc.fbm_externalleadbidders , dd.fbm_externalleadbidders )  fbm_externalleadbidders,
        CASE
            WHEN cc.candidate_source IS NOT NULL AND dd.candidate_source IS NOT NULL THEN "construct_connect & dodge"
            ELSE COALESCE(cc.candidate_source, dd.candidate_source)
        END AS  candidate_source
       FROM cc_data AS cc FULL OUTER JOIN dodge_data AS dd
       ON cc.primary_project_id = dd.primary_project_id

"""

CONSOLIDATED_PRIMARY_PROJECT_QUERY ="""
-- Fetch all projects from the primary_project_lead
-- create table sales_recommender_dev.test_1 as
WITH
  project_candidates AS (
    SELECT
      batch_id,
      primary_project_id,
      mg.project_id AS candidate_project_id,
      mg.project_source AS candidate_source,
      mg.sourceFileCreationTime AS candidate_creation_time
    FROM
      `{primary_lead_table_path}`,
      UNNEST(matched_group) AS mg
    WHERE
      batch_id = @batch_id
  ),
  
  -- Process and shape ConstructConnect data in a single step
  construct_connect_final AS (
    SELECT
      pc.batch_id,
      pc.primary_project_id,
      pc.candidate_source,
      cc.ProjectID,
      cc.Title,
      cc.Stage,
      cc.URL,
      cc.Valuation_Value,
      cc.Parameters_Parameter_Ownership,
      cc.Parameters_Parameter_BidDate,
      cc.Parameters_Parameter_BidTime,
      cc.Parameters_Parameter_WorkType,
      cc.Parameters_Parameter_Structures,
      cc.DocumentAvailability_Plans,
      cc.DocumentAvailability_Specs,
      cc.DocumentAvailability_Addenda,
      cc.ParentCategories_PrimaryCategoryName,
      cc.ParentCategories_ParentCategory,
      cc.Addresses_Address,
      cc.Details_Detail_Scope,
      cc.Details_Detail_Notes,
      cc.Details_Detail,
      cc.Materials_Material,
      cc.RSMeansMaterialDivisions_Division_Metals,
      cc.RSMeansMaterialDivisions_Division_ThermalandMoistureProtection,
      cc.RSMeansMaterialDivisions_Division_Openings,
      cc.RSMeansMaterialDivisions_Division_Finishes,
      cc.RSMeansMaterialDivisions_Division_Masonry,
      DATE(cc.Parameters_Parameter_CommenceDate) AS Parameters_Parameter_CommenceDate,
      cc.Parameters_Parameter_FloorArea,
      cc.sourceFileCreationTime,
      -- Extract first GC company details
      (
        SELECT AS STRUCT
          LEFT(company.name, 50) AS companyname,
          LEFT(company.Addresses.Address [SAFE_OFFSET(0)].City, 50) AS address1_city,
          LEFT(company.Addresses.Address [SAFE_OFFSET(0)].StateProvince, 50) AS address1_stateorprovince,
          LEFT(company.Addresses.Address [SAFE_OFFSET(0)].County, 50) AS address1_county,
          LEFT(company.Email, 50) AS emailaddress1,
          (
            SELECT ph.PhoneNumnber
            FROM UNNEST(company.Phones.phone) AS ph
            WHERE ph.PhoneType = 'Company Phone Number'
          ) AS mobilephone,
          LEFT(SPLIT(company.Contacts.Contact [SAFE_OFFSET(0)].Name, ' ') [SAFE_OFFSET(0)], 50) AS firstname,
          LEFT(SPLIT(company.Contacts.Contact [SAFE_OFFSET(0)].Name, ' ') [SAFE_OFFSET(1)], 50) AS lastname
        FROM UNNEST(cc.Companies) AS company_wrap, UNNEST(company_wrap.Company) AS company
        WHERE company.BiddingRole = 'General Contractor'
        ORDER BY company.Name
        LIMIT 1
      ) AS GC_company,
      -- Generate bidder list
      (
        SELECT STRING_AGG(
          (
            SELECT STRING_AGG(
              FORMAT(
                '{{"Company Name":"%s","Name":%s,"Email":%s,"PhoneNumber":%s}}',
                company.Name,
                IF(contact.Name IS NULL, 'null', FORMAT('"%s"', contact.Name)),
                IF(contact.Email IS NULL, 'null', FORMAT('"%s"', contact.Email)),
                IF(contact.PhoneNumber IS NULL, 'null', FORMAT('"%s"', contact.PhoneNumber))
              ), ','
            ) FROM UNNEST(company.contacts.contact) AS contact
          ), '\\n'
        )
        FROM UNNEST(cc.Companies) AS company_wrap, UNNEST(company_wrap.Company) AS company
        WHERE company.BiddingRole = 'General Contractor'
      ) AS fbm_externalleadbidders
    FROM project_candidates AS pc
    JOIN `{cc_feed_table_path}`  AS cc
      ON pc.candidate_project_id = cc.ProjectID AND pc.candidate_creation_time = cc.sourceFileCreationTime
    WHERE pc.candidate_source = 'construct_connect'
  ),

  -- Process and shape Dodge data in a single step
  dodge_final AS (
    SELECT
      pc.batch_id,
      pc.primary_project_id,
      pc.candidate_source,
      dodge.DRNumber AS ProjectID,
      dodge.ProjectTitle AS Title,
      dodge.PrimaryStage AS Stage,
      dodge.ProjectURL AS URL,
      dodge.Valuation AS Valuation_Value,
      dodge.OwnershipType AS Parameters_Parameter_Ownership,
      CAST(dodge.BidDate AS STRING) AS Parameters_Parameter_BidDate,
      CAST(NULL AS STRING) AS Parameters_Parameter_BidTime,
      dodge.TypeOfWork AS Parameters_Parameter_WorkType,
      NULL AS Parameters_Parameter_Structures,
      LOWER(dodge.PlanAvailable) = 'yes' AS DocumentAvailability_Plans,
      LOWER(dodge.SpecAvailable) = 'yes' AS DocumentAvailability_Specs,
      CAST(NULL AS BOOL) AS DocumentAvailability_Addenda,
      dodge.PrimaryProjectType AS ParentCategories_PrimaryCategoryName,
      [STRUCT(dodge.MarketSegment AS Name, STRUCT(CAST(NULL AS ARRAY<STRING>) AS SubCategory) AS SubCategories)] AS ParentCategories_ParentCategory,
      [STRUCT("Project" AS ProjectAddressType, dodge.Address AS AddressLine1, "" AS AddressLine2, dodge.City, dodge.Country AS CountryRegion, dodge.County, CAST(dodge.Lat AS NUMERIC) AS Latitude, CAST(dodge.Long AS NUMERIC) AS Longitude, dodge.State AS StateProvince, dodge.Zip AS ZipPostalCode)] AS Addresses_Address,
      CAST(NULL AS ARRAY<STRING>) AS Details_Detail_Scope,
      CAST(NULL AS ARRAY<STRING>) AS Details_Detail_Notes,
      IF(dodge.FeaturesInfo IS NOT NULL, [STRUCT('Detail' AS DetailType, dodge.FeaturesInfo AS Detail)], []) AS Details_Detail,
      CAST(NULL AS ARRAY<STRUCT<Code INT64, _ STRING>>) AS Materials_Material,
      CAST(NULL AS ARRAY<STRUCT<Code INT64, InstallationCostValue NUMERIC, MaterialCostValue NUMERIC, TotalCostValue NUMERIC, _ STRING>>) AS RSMeansMaterialDivisions_Division_Metals,
      CAST(NULL AS ARRAY<STRUCT<Code INT64, InstallationCostValue NUMERIC, MaterialCostValue NUMERIC, TotalCostValue NUMERIC, _ STRING>>) AS RSMeansMaterialDivisions_Division_ThermalandMoistureProtection,
      CAST(NULL AS ARRAY<STRUCT<Code INT64, InstallationCostValue NUMERIC, MaterialCostValue NUMERIC, TotalCostValue NUMERIC, _ STRING>>) AS RSMeansMaterialDivisions_Division_Openings,
      CAST(NULL AS ARRAY<STRUCT<Code INT64, InstallationCostValue NUMERIC, MaterialCostValue NUMERIC, TotalCostValue NUMERIC, _ STRING>>) AS RSMeansMaterialDivisions_Division_Finishes,
      CAST(NULL AS ARRAY<STRUCT<Code INT64, InstallationCostValue NUMERIC, MaterialCostValue NUMERIC, TotalCostValue NUMERIC, _ STRING>>) AS RSMeansMaterialDivisions_Division_Masonry,
      dodge.TargetStartDate AS Parameters_Parameter_CommenceDate,
      CAST(dodge.SquareFootage AS FLOAT64) AS Parameters_Parameter_FloorArea,
      dodge.sourceFileCreationTime,
      -- Extract GC company details
      (
        SELECT AS STRUCT
          company.CompanyName AS companyname,
          company.CompanyCity AS address1_city,
          company.CompanyState AS address1_stateorprovince,
          company.CompanyCounty AS address1_county,
          company.ContactEmail AS emailaddress1,
          company.ContactPhone AS mobilephone,
          SPLIT(company.ContactName, ' ') [SAFE_OFFSET(0)] AS firstname,
          SPLIT(company.ContactName, ' ') [SAFE_OFFSET(1)] AS lastname
        FROM UNNEST(dodge.Companies.Company) AS company
        WHERE company.FactorType = 'General Contractor'
        ORDER BY company.CompanyName
        LIMIT 1
      ) AS GC_company,
      -- Generate bidder list
      (
        SELECT STRING_AGG(
            FORMAT('{{"Company Name":"%s","Name":%s,"Email":%s,"PhoneNumber":%s }}', company.CompanyName, IF(company.ContactName IS NULL, 'null', FORMAT('"%s"', company.ContactName)), IF(company.ContactEmail IS NULL, 'null', FORMAT('"%s"', company.ContactEmail)), IF(company.ContactPhone IS NULL, 'null', FORMAT('"%s"', company.ContactPhone))), '\\n'
        )
        FROM UNNEST(dodge.Companies.Company) AS company
        WHERE company.FactorType = 'General Contractor'
      ) AS fbm_externalleadbidders
    FROM project_candidates AS pc
    JOIN `{dodge_feed_table_path}` AS dodge
      ON pc.candidate_project_id = dodge.DRNumber AND pc.candidate_creation_time = dodge.sourceFileCreationTime
    WHERE pc.candidate_source = 'dodge'
  )

-- Final selection 
SELECT
  * 
FROM (
  SELECT * FROM construct_connect_final
  UNION ALL
  SELECT * FROM dodge_final
);
"""
# Query to get 'match' projects for grouping
DUPLICATE_PROJECTS_QUERY = """
    SELECT
        batch_id,
        STRUCT(project_id, project_source, sourceFileCreationTime, TRUE AS delta_record ,existing_primary_project_id) AS project,
        STRUCT(potential_match_id, potential_match_source, potential_match_sourceFileCreationTime, FALSE AS delta_record, existing_primary_project_id) AS potential_match_project,
        llm_result
    FROM `{table_path}`
    WHERE batch_id = @batch_id AND llm_result = @match_status
"""


# Query to get 'unsure' projects
POTENTIAL_MATCH_PROJECTS_QUERY = """
    SELECT
        batch_id,
        STRUCT(project_id, project_source, sourceFileCreationTime, TRUE AS delta_record) AS project,
        STRUCT(potential_match_id, potential_match_source, potential_match_sourceFileCreationTime, FALSE AS delta_record) AS potential_match_project,
        llm_result
    FROM `{table_path}`
    WHERE batch_id = @batch_id AND llm_result = @match_status
"""

# Query to insert linked sources from the primary lead table
INSERT_SOURCE_LINKING_QUERY = """
    INSERT INTO `{target_table_path}` (primary_project_id, batch_id, match_status, source_project_id, source, sourceFileCreationTime, delta_record)
    SELECT
        primary_project_id,
        batch_id,
        match_status,
        mg.project_id AS source_project_id,
        mg.project_source AS source,
        mg.sourceFileCreationTime,
        mg.delta_record
    FROM `{source_table_path}`
    CROSS JOIN UNNEST(matched_group) AS mg
    WHERE batch_id = @batch_id AND match_status IN (@match, @unsure)
"""

# Query to insert unique ('no_match') projects directly into the primary lead table
INSERT_UNIQUE_PROJECTS_QUERY = """
    INSERT INTO `{target_table_path}` (primary_project_id, batch_id, match_status, matched_group)
    SELECT
        coalesce(existing_primary_project_id, GENERATE_UUID()) AS primary_project_id,
        batch_id,
        llm_result AS match_status,
        [STRUCT(project_id, project_source AS source_project_id, sourceFileCreationTime, TRUE AS delta_record)] AS matched_group
    FROM `{source_table_path}`
    WHERE batch_id = @batch_id AND llm_result = @no_match_status
"""

# Query to get location data for unique projects
UNIQUE_PROJECT_CANDIDATES_QUERY = """
    WITH project_candidates AS (
        SELECT primary_project_id, mg
        FROM `{primary_lead_table_path}`
        CROSS JOIN UNNEST(matched_group) AS mg
        WHERE batch_id = @batch_id AND mg.delta_record = @delta
    )
    SELECT
        primary_project_id AS ProjectID,
        mg.sourceFileCreationTime,
        COALESCE(cc.Addresses_Address[SAFE_OFFSET(0)].Longitude, CAST(dd.Long AS NUMERIC)) AS Longitude,
        COALESCE(cc.Addresses_Address[SAFE_OFFSET(0)].Latitude, CAST(dd.Lat AS NUMERIC)) AS Latitude
    FROM project_candidates
    LEFT JOIN `{cc_feed_table_path}` AS cc
        ON mg.project_source = 'construct_connect'
        AND mg.project_id = cc.projectID
        AND mg.sourceFileCreationTime = cc.sourceFileCreationTime
    LEFT JOIN `{dodge_feed_table_path}` AS dd
        ON mg.project_source = 'dodge'
        AND mg.project_id = dd.DRNumber
        AND mg.sourceFileCreationTime = dd.sourceFileCreationTime
"""

# Query to get territories
TERRITORIES_QUERY = "SELECT id AS territory_id, latitude AS lat, longitude AS lon FROM `{table_path}`"

# Query to get searches
SEARCHES_QUERY = """
    SELECT s.id AS search_id, st.territory_id
    FROM `{searches_table_path}` AS s
    LEFT JOIN `{search_territory_table_path}` AS st
        ON s.id = st.search_id
    WHERE LOWER(s.name) != 'core'
"""

EXISTING_PRIMARY_PROJECTID_QUERY = """
MERGE INTO `{target_table_path}` llm
USING (
	SELECT primary_project_id,
		mg.project_id
	FROM `{source_table_path}`,
		unnest(matched_group) mg 
        QUALIFY  ROW_NUMBER() OVER ( PARTITION BY mg.project_id ORDER BY sourceFileCreationTime DESC) = 1
	) ppl
	ON batch_id = @batch_id
		AND CASE 
			WHEN llm.project_id = ppl.project_id THEN 1
			WHEN llm.potential_match_id = ppl.project_id AND llm.llm_result = 'match' THEN 2
			ELSE 3
			END = 1
WHEN MATCHED
	THEN
		UPDATE
		SET existing_primary_project_id = primary_project_id;
"""