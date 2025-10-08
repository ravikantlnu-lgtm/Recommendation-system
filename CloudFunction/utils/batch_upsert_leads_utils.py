from services import BigQueryManager, DynamicsManager
import pandas as pd
import numpy as np
from google.cloud import bigquery
import requests
from config import Settings
import concurrent.futures
from tqdm import tqdm
import uuid
import json
from logging_config import log_default, log_error

# Consolidated column mapping with external lead columns
external_lead_col_mapping = {
    "batch_id": "fbm_batchid",
    "candidate_source": "fbm_candidatesource",
    "Details_Detail": "fbm_detailsdetail",
    "Details_Detail_Notes": "fbm_detailsdetailnotes",
    "Details_Detail_Scope": "fbm_detailsdetailscope",
    "DocumentAvailability_Addenda": "fbm_documentavailabilityaddenda",
    "DocumentAvailability_Plans": "fbm_documentavailabilityplans",
    "DocumentAvailability_Specs": "fbm_documentavailabilityspecs",
    "Materials_Material": "fbm_materialsmaterial",
    "Parameters_Parameter_BidDate": "fbm_parametersparameterbiddate",
    "Parameters_Parameter_CommenceDate": "fbm_parametersparametercommencedate",
    "Parameters_Parameter_FloorArea": "fbm_parametersparameterfloorarea",
    "Parameters_Parameter_Ownership": "fbm_parametersparameterownership",
    "Parameters_Parameter_Structures": "fbm_parametersparameterstructures",
    "Parameters_Parameter_WorkType": "fbm_parametersparameterworktype",
    "ParentCategories_ParentCategory": "fbm_parentcategoriesparentcategory",
    "ParentCategories_PrimaryCategoryName": "fbm_parentcategoriesprimarycategoryname",
    "primary_project_id": "fbm_primaryprojectid",
    "ProjectID": "fbm_projectid",
    "RSMeansMaterialDivisions_Division_Masonry": "fbm_rsmmddivisionmasonry",
    "RSMeansMaterialDivisions_Division_Metals": "fbm_rsmmddivisionmetals",
    "RSMeansMaterialDivisions_Division_Openings": "fbm_rsmmddivisionopenings",
    "RSMeansMaterialDivisions_Division_ThermalandMoistureProtection": "fbm_rsmmddivisionthermalandmoistureprotection",
    "sourceFileCreationTime": "fbm_sourcefilecreationtime",
    "Stage": "fbm_stage",
    "URL": "fbm_url",
    "Valuation_Value": "fbm_valuationvalue",
    "AddressLine1": "fbm_addressline1",
    "AddressLine2": "fbm_addressline2",
    "City": "fbm_city",
    "CountryRegion": "fbm_countryregion",
    "County": "fbm_county",
    "Latitude": "fbm_latitude",
    "Longitude": "fbm_longitude",
    "ProjectAddressType": "fbm_projectaddresstype",
    "StateProvince": "fbm_stateprovince",
    "ZipPostalCode": "fbm_zippostalcode"
}

def _load_batch_upsert_lead_table(
	backfill,
	search_ids,
	settings,
	sales_profile_temp,
	FILE_PATH,
	big_query_client,
    batch_id
):
     
    # Fetching project_relevance project related only to Delta_file/backfill projects.
    if backfill:
		# If backfill is true then only get project relevance for backfill projects.
        search_id_filter = ''
        if search_ids:
            search_id_filter = ','.join(f"'{id}'" for id in search_ids.split(','))
            search_id_filter = f" AND searches.id IN ({search_id_filter})" 
    else:
        search_id_filter =''

    create_unique_combination_query = CREATE_UNIQUE_COMBINATION_QUERY.format(
        data_set = settings.BIGQUERY_DATASET,
        project_relevance_table = settings.PROJECT_RELEVANCE_TABLE_ID,
        searches_table = settings.SEARCHES_TABLE_ID,
        sales_profile_temp = sales_profile_temp,
        default_sales_rep_id = settings.DM_DEFAULT_SALES_REP_ID,
        search_id_filter = search_id_filter,
        batch_id= batch_id
    )
	# create_unique_combination_query: This query retrieves project relevance data,
	# and generates unique project_id-search_id-sales_rep combinations.
    result = big_query_client.query_table(query=create_unique_combination_query, to_dataframe=True)


	# Replace NaN values with None
    result = result.replace({np.nan: None})

    # Sorting the records and adding a row_no column to the DataFrame.
    result = result.sort_values(by=["project_id", "search_id", "sales_rep_id"], ascending=[True, True, True])
    result["row_no"] = range(1, len(result) + 1)

	# Define the job configuration
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE
    )
    # Creating batch_upsert_leads using dataframe.
    big_query_client.load_from_dataframe(
        table_id = f"batch_upsert_leads",
        dataframe = result,
        job_config = job_config

        )

def get_relevance_code(relevance_string):
    """Convert text relevance to numeric code"""
    relevance_dict = {
        "very high": 866070000,
        "high": 866070001,
        "moderate": 866070002,
        "low": 866070003,
        "very low": 866070004,
        "unsure": 866070005,
        "not relevant": 866070006,
    }
    return relevance_dict[relevance_string.lower()]

def get_source_code(source):
    """Convert text relevance to crm numeric code"""
    source_code_dict ={
        "construct_connect" :110 ,
        "dodge": 866070002,
        "construct_connect & dodge": 866070001,
    }
    return source_code_dict[source.lower()]

def fetch_sales_rep_info(
    dynamics_client: DynamicsManager,
    big_query_client: BigQueryManager,
    settings: Settings,
    sales_profile_temp_table_id: str
    
):
    """
    Fetches sales representative information from Dynamics CRM and loads it into a temporary BigQuery Table.
    This function retrieves data from the fbm_usersalesprofileset and fbm_salesbranchset Dynamics CRM tables, 
    """


    sales_profile_data = dynamics_client.get_data( settings.DM_USERSALESPROFILESET, paginate=True )
    sales_profile_df = pd.DataFrame( sales_profile_data.get("value", []))
    if not sales_profile_df.empty:
        sales_profile_df = sales_profile_df[['systemuserid', 'fbm_searchid']]

    # sales_branch_set table.
    branch_data = dynamics_client.get_data( settings.DM_SALESBRANCHSET, paginate=True)
    branch_df = pd.DataFrame( branch_data.get("value", []))
    if not branch_df.empty:
        branch_df = branch_df[['systemuserid','teamid']]

    if not sales_profile_df.empty or not branch_df.empty:
        # Left Join with branch_df
        final_df = pd.merge(sales_profile_df, branch_df, left_on='systemuserid', right_on='systemuserid', how='left')


        # Replace NaN values with None
        final_df = final_df.replace({np.nan: None})

        # selecting ownerid , searchid and territoryid columns which are required to create combination of leads.
        final_df = final_df[['systemuserid','fbm_searchid','teamid']].rename(
            columns={
                "systemuserid": "_ownerid_value"
                ,"fbm_searchid": "_fbm_searchid_value"
                ,"teamid": "_fbm_branchid_value"
            }
        )
    else:
        final_df = pd.DataFrame(columns=["_ownerid_value","_fbm_searchid_value","_fbm_branchid_value"])
        final_df = final_df.astype(str)

    schema = [
        bigquery.SchemaField("_ownerid_value", "STRING"),
        bigquery.SchemaField("_fbm_searchid_value", "STRING"),
        bigquery.SchemaField("_fbm_branchid_value", "STRING"),
    ]
    job_config = bigquery.LoadJobConfig(
        create_disposition=bigquery.CreateDisposition.CREATE_IF_NEEDED,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        schema=schema
    )
    
    # Load sales profile data into temp bigquery table.
    big_query_client.load_from_dataframe(
        table_id=sales_profile_temp_table_id,
        dataframe=final_df,
        job_config=job_config
    )


def get_existing_branchopportunity(
	dynamics_client : DynamicsManager, 
    combinations: list, 
    settings: Settings,
    chunck_size: int = 100
):
    """Get existing lead data from Dynamics CRM"""
    def get_branchopportunity(combinations):
        filter_ls = []
        for uc in combinations:
            filter_ls.append(
                f"""( _fbm_lead_value eq '{uc.get("leadid")}' and _fbm_productcategoryid_value eq '{uc.get("fbm_productcategoryid")}' and _fbm_branchid_value eq '{uc.get("fbm_branchid")}')"""
            )

        filter_by = " or ".join(filter_ls)

        select_by = [ "fbm_branchopportunityid", "_fbm_lead_value", "_fbm_productcategoryid_value", "_fbm_branchid_value"]

        query_params = {"$filter": filter_by, "$select": ",".join(select_by)}

        url = f"{dynamics_client.domain}/{dynamics_client.api_path}/{settings.DM_BRANCH_OPPORTUNITY_ID}"
        headers = dynamics_client.headers
        try:
            response = requests.get(url, headers=headers, params=query_params)
            response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
            response = response.json()
        except requests.exceptions.RequestException as e:
            if "response" in locals() and response is not None:
                raise requests.exceptions.RequestException(
                    f"GET Request Error: {e}\n"
                    f"Response status code: {response.status_code}\n"
                    f"Response body: {response.text if response.content else 'No content'}"
                )
            raise requests.exceptions.RequestException(f"GET Request Error: {e}\n")

        already_exists_branch_opportunity = {}
        for branch_opportunity in response["value"]:
            fbm_branchopportunityid = branch_opportunity["fbm_branchopportunityid"]
            leadid = branch_opportunity["_fbm_lead_value"]
            fbm_productcategoryid = branch_opportunity["_fbm_productcategoryid_value"]
            fbm_branchid = branch_opportunity["_fbm_branchid_value"]
            

            key = (leadid, fbm_productcategoryid, fbm_branchid)
            already_exists_branch_opportunity[key] = {
                "fbm_branchopportunityid": fbm_branchopportunityid
            }

        return already_exists_branch_opportunity
    
    already_exists_branch_opportunity = {}

    for i in range(0, len(combinations), chunck_size):
        chunk = combinations[i : i + chunck_size]
        already_exists_branch_opportunity |= get_branchopportunity(chunk )

    return already_exists_branch_opportunity

def separate_update_insert_branchopportunity(already_exists_branchopportunity, branchopportunities):
    """Separate opportunities into insert and update lists based on existing data"""
    insert_opportunities, update_opportunities = [], []

    for uc in branchopportunities:
        key = (uc["leadid"], uc["fbm_productcategoryid"], uc["fbm_branchid"])
        record = {
            "leadid": uc["leadid"],
            "fbm_productcategoryid": uc["fbm_productcategoryid"],
            "fbm_estimatedrevenue": uc["fbm_estimatedrevenue"],
            "fbm_branchid": uc["fbm_branchid"],
        }

        if key in already_exists_branchopportunity:
            record["fbm_branchopportunityid"] = already_exists_branchopportunity[key]["fbm_branchopportunityid"]
            update_opportunities.append(record)
        else:
            insert_opportunities.append(record)

    return insert_opportunities, update_opportunities

def build_batch_opportunities( insert_opportunities ):
    batch_data = []
    for record in insert_opportunities:
        data = {}
        # pr = project_relevance_data_map.get((record["project_id"], record["search_id"]))
        new_branchopportunityid = record.get('fbm_branchopportunityid',uuid.uuid4())

        data = {
            "fbm_branchopportunityid": str(new_branchopportunityid),
            "fbm_Lead@odata.bind": f"/leads({record['leadid']})",
            "fbm_productcategoryid@odata.bind": f"/fbm_productcategories({record['fbm_productcategoryid']})",
            "fbm_branchId@odata.bind": f"/teams({record['fbm_branchid']})",
            "fbm_estimatedrevenue": record['fbm_estimatedrevenue']
        }
        
        batch_data.append(data)
    return batch_data



def process_batches_concurrently(
    data_to_process,
    method,
    operation_desc,
    batch_size=100,
    max_workers=5,
    **kwargs
):
    """
    Handles concurrent batch processing of data using a ThreadPoolExecutor.

    Args:
        data_to_process (list): The data to be processed in batches.
        method (function): The client function to execute for each batch 
                                  (e.g., dynamics_client.send_batch_create).
        operation_desc (str): A string describing the operation (e.g., "insert", "update")
                              for logging and the progress bar.
        entity_name (str): The target entity name for the API call.
        batch_size (int): The number of items in each batch.
        max_workers (int): The number of concurrent threads to use.
        *kwargs: Additional positional arguments to pass to the client_method.
    """
    if not data_to_process:
        print(f"No data to process for {operation_desc}.")
        return
    futures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        for i in range(0, len(data_to_process), batch_size):
            chunk = data_to_process[i : i + batch_size]
            # Submit the task with the chunk and any other specific args
            future = executor.submit(
                method, chunk,  **kwargs
            )
            futures.append(future)

    # Use tqdm for a progress bar while iterating through completed futures
    for future in tqdm(
        concurrent.futures.as_completed(futures),
        total=len(futures),
        desc=f"batch {operation_desc} leads",
    ):
        try:
            # future.result() will re-raise any exception caught during execution
            response = future.result()
        except Exception as e:
            raise Exception(e)

def add_bullets(text):
    lines = text.strip().split('\n')
    bullet_lines = [f"• {line.strip()}" for line in lines if line.strip()]
    return ' \n'.join(bullet_lines) 


def get_project_details(
    settings: Settings,
    event: dict,
    bq_client:BigQueryManager
) -> dict :
    batch_id = event['batch_id']
    coalesced_table_id=f"{settings.BIGQUERY_DATASET}.{settings.COALESCED_PRIMARY_PROJECT_TABLE_ID}"
    
    query = f"""
        SELECT 
            ProjectID AS fbm_externalleadid,
            Title AS arb_project_name,
            Stage AS fbm_projectstage,
            Parameters_Parameter_BidDate AS fbm_biddate,
            Valuation_Value AS fbm_estimatedprojectvalue,
            CAST(Parameters_Parameter_CommenceDate AS STRING) AS fbm_startdate,
            CAST(sourceFileCreationTime as STRING) AS fbm_lastsyncdate,

            -- Mapped Address fields from the *first* element of the Addresses_Address array
            Addresses_Address[SAFE_OFFSET(0)].AddressLine1 AS arb_project_line1,
            Addresses_Address[SAFE_OFFSET(0)].AddressLine2 AS arb_project_line2,
            Addresses_Address[SAFE_OFFSET(0)].City AS arb_project_city,
            Addresses_Address[SAFE_OFFSET(0)].StateProvince AS arb_project_stateorprovince,
            Addresses_Address[SAFE_OFFSET(0)].ZipPostalCode AS arb_project_postalcode,
            Addresses_Address[SAFE_OFFSET(0)].CountryRegion AS arb_project_country,
            CAST(`Addresses_Address`[SAFE_OFFSET(0)].Longitude AS STRING) AS fbm_project_address_long,
            CAST(`Addresses_Address`[SAFE_OFFSET(0)].Latitude AS STRING) AS fbm_project_address_lat,

            -- Mapped Lead Facts/Notes (Concatenated)
            ARRAY_TO_STRING(Details_Detail_Scope, '\\n') AS fbm_projectdescription,

            -- Mapped Categories
            -- ParentCategories_PrimaryCategoryName AS fbm_ProjectCategories,
            (SELECT STRING_AGG(pc.Name, ', ') FROM UNNEST(ParentCategories_ParentCategory) pc) AS fbm_projectcategories,
            -- Mapped Link To CMD Lead
            URL AS fbm_externalleadurl,

            -- Mapped Document Availability
            DocumentAvailability_Plans AS fbm_plansavailable,
            DocumentAvailability_Specs AS fbm_specificationsavailable,
            DocumentAvailability_Addenda AS fbm_addendaavailable,

            -- Mapped Work Type
            Parameters_Parameter_WorkType AS fbm_worktype,

            -- Mapped Square Footage Information
            CAST(Parameters_Parameter_FloorArea AS STRING) AS arb_totalsquarefootage,
            -- Fields extracted from the aggregated General Contractor company struct
            LEFT(GC_company.companyname, 50) AS companyname,
            LEFT( GC_company.address1_city, 50 ) AS address1_city,
            LEFT( GC_company.address1_stateorprovince,50 ) AS address1_stateorprovince,
            LEFT( GC_company.address1_county, 50 ) AS address1_county,
            LEFT(GC_company.emailaddress1, 50) AS emailaddress1,
            
            GC_company.mobilephone AS mobilephone,
            LEFT( GC_company.firstname, 50 ) AS firstname,
            LEFT( GC_company.lastname,50  ) AS lastname,
            -- Aggregated bidder list
            fbm_externalleadbidders AS fbm_externalleadbidders,
            candidate_source AS arb_leadsourcecode
        FROM `{coalesced_table_id}`
        WHERE batch_id = '{batch_id}'
    """

    result = bq_client.query_table(query=query)

    project_details_dict = {}
    for row in result:
        row = dict(row)
        row["fbm_externalleadid"] = str(row["fbm_externalleadid"])
        row["fbm_estimatedprojectvalue"] = (
            float(row["fbm_estimatedprojectvalue"]) if row["fbm_estimatedprojectvalue"] else None
        )
        row["fbm_projectdescription"] = row["fbm_projectdescription"][:2000]
        project_details_dict[row["fbm_externalleadid"]] = dict(row)

    return project_details_dict

def get_existing_external_lead(
    dynamics_client : DynamicsManager, 
    combinations: list, 
    settings: Settings,
    chunck_size: int = 100
):
    """Get existing external_lead data from Dynamics CRM"""
    def get_external_lead(combinations):
        filter_ls = []
        for uc in combinations:
            filter_ls.append(
                f"""( fbm_projectid eq {uc.get("fbm_projectid")} and fbm_primaryprojectid eq '{uc.get("fbm_primaryprojectid")}')"""
            )

        filter_by = " or ".join(filter_ls)

        select_by = [ "fbm_externalleadid", "fbm_projectid", "fbm_primaryprojectid"]

        query_params = {"$filter": filter_by, "$select": ",".join(select_by)}

        url = f"{dynamics_client.domain}/{dynamics_client.api_path}/{settings.DM_EXTERNALLEAD_ID}s"
        headers = dynamics_client.headers
        try:
            response = requests.get(url, headers=headers, params=query_params)
            response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
            response = response.json()
        except requests.exceptions.RequestException as e:
            if "response" in locals() and response is not None:
                raise requests.exceptions.RequestException(
                    f"GET Request Error: {e}\n"
                    f"Response status code: {response.status_code}\n"
                    f"Response body: {response.text if response.content else 'No content'}"
                )
            raise requests.exceptions.RequestException(f"GET Request Error: {e}\n")

        already_exists_external_lead = {}
        for lead in response["value"]:
            fbm_externalleadid = lead["fbm_externalleadid"]
            fbm_projectid = lead["fbm_projectid"]
            fbm_primaryprojectid = lead["fbm_primaryprojectid"]
            

            key = (fbm_primaryprojectid, str(fbm_projectid))
            already_exists_external_lead[key] = {
                "fbm_externalleadid": fbm_externalleadid
            }

        return already_exists_external_lead
    
    already_exists_external_lead = {}

    for i in range(0, len(combinations), chunck_size):
        chunk = combinations[i : i + chunck_size]
        already_exists_external_lead |= get_external_lead(chunk )

    return already_exists_external_lead

def separate_update_insert_external_lead(
        already_exists_leads: dict,
        consolidated_project: list
):
    """Separate external_leads into insert and update lists based on existing data"""
    insert_leads, update_leads = [], []

    for uc in consolidated_project:
        key = (uc["fbm_primaryprojectid"], uc["fbm_projectid"])
        record = uc

        if key in already_exists_leads:
            record['fbm_externalleadid'] = already_exists_leads[key]['fbm_externalleadid']
            update_leads.append(record)
        else:
            record['fbm_externalleadid'] = str(uuid.uuid4())
            insert_leads.append(record)
    return insert_leads, update_leads


def push_consolidated_data(
    dynamics_client: DynamicsManager,
    big_query_client: BigQueryManager,
    settings: Settings,
    batch_id: str,
    log_context: dict,
):
    schema = big_query_client.get_schema(settings.CONSOLIDATED_PRIMARY_PROJECT_LEAD_TABLE_ID)
    select_expressions = []
    for field in schema:
        # Use TO_JSON_STRING for ANY complex type (arrays or records)
        if field.mode == 'REPEATED' or field.field_type == 'RECORD':
            expression = f"TO_JSON_STRING({field.name}) AS {field.name}"
        else:
            expression = f"CAST({field.name} AS STRING) AS {field.name}"
        select_expressions.append(expression)

    final_select_statement = ",\n ".join(select_expressions)

    table_path = f"{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.{settings.CONSOLIDATED_PRIMARY_PROJECT_LEAD_TABLE_ID}"
    # --- 3. Construct and run the final query ---
    query_params = [
        bigquery.ScalarQueryParameter("batch_id", "STRING", batch_id)
    ]
    job_config = bigquery.QueryJobConfig(query_parameters=query_params)
    query = f"""
        SELECT
            {final_select_statement}
        FROM `{table_path}`
        WHERE batch_id = @batch_id;
    """
    df = big_query_client.query_table(query=query, job_config=job_config, to_dataframe=True)
    df_flat = df['Addresses_Address'].apply(lambda x: json.loads(x)[0] if x else {})
    df_flat = pd.json_normalize(df_flat)
    df = pd.concat([df.drop(columns=['Addresses_Address','GC_company','Title','Parameters_Parameter_BidTime','RSMeansMaterialDivisions_Division_Finishes','fbm_externalleadbidders']), df_flat], axis=1)

    df.rename(columns=external_lead_col_mapping, inplace=True)
    df.replace("[]", None, inplace=True)

    col_max_lenght_dict = {'fbm_addressline1': 1000, 'fbm_addressline2': 1000, 'fbm_detailsdetail': 8000, 'fbm_detailsdetailnotes': 8000, 'fbm_detailsdetailscope': 8000, 'fbm_materialsmaterial': 8000, 'fbm_parametersparameterownership': 1000, 'fbm_parametersparameterworktype': 1000, 'fbm_parentcategoriesparentcategory': 6000, 'fbm_parentCategoriesprimarycategoryname': 3000, 'fbm_projectaddresstype': 1000, 'fbm_rsmmddivisionmasonry': 10000, 'fbm_rsmmddivisionmetals': 10000, 'fbm_rsmmddivisionopenings': 10000, 'fbm_rsmmddivisionthermalandmoistureprotection': 10000}

    for col, max_len in col_max_lenght_dict.items():
        if col in df.columns:
            df[col] = df[col].astype(str).str[:max_len]

    consolidated_project_ls = df.to_dict(orient='records')

    already_exists_external_lead = get_existing_external_lead(dynamics_client, consolidated_project_ls, settings)

    insert_leads, update_leads =separate_update_insert_external_lead(already_exists_external_lead, consolidated_project_ls)


    log_default(
        log_message=f"external_leads to insert: {len(insert_leads)}  and external_leads to update: {len(update_leads)}",
        json_payload=json.dumps(log_context),
    )
    if len(insert_leads) > 0:
        log_default( log_message=f"Batch insert external_leads started.", json_payload=json.dumps( log_context) )
        process_batches_concurrently(
            data_to_process= insert_leads,
            method=dynamics_client.send_batch_create,
            operation_desc= "batch insert external_leads",
            entity_name = f"{settings.DM_EXTERNALLEAD_ID}s"
        )
        log_default( log_message=f"Batch insert external_leads completed.", json_payload=json.dumps(log_context))

    if len(update_leads) > 0:
        # Executing 10 concurrent batch update to reduce overall execution time.
        log_default(log_message=f"Batch update external_leads.", json_payload=json.dumps(log_context) )
        
        process_batches_concurrently(
            data_to_process= update_leads,
            method=dynamics_client.send_batch_update,
            operation_desc= "batch update external_leads",
            entity_name = f"{settings.DM_EXTERNALLEAD_ID}s",
            primary_key = "fbm_externalleadid"
        )                        
        
        log_default(log_message=f"Batch update external_leads completed.", json_payload=json.dumps( log_context) )
    
    external_lead_df = pd.DataFrame(insert_leads + update_leads)

    return external_lead_df

# create_unique_combination_query: This query retrieves project relevance data,
# and generates unique project_id-search_id-sales_rep combinations.
CREATE_UNIQUE_COMBINATION_QUERY ="""
WITH project_relevance_cte
AS ( -- This CTE Fetches the project relevance data of delta file.
	SELECT pr.*
	FROM `{data_set}.{project_relevance_table}` pr
	INNER JOIN `{data_set}.{searches_table}` searches 
  ON pr.search_id = searches.id
  WHERE batch_id = '{batch_id}' AND distance <= 60 -- Only include core rows within 60 miles
  {search_id_filter}

	),
batch_upsert_leads
AS (  
	SELECT * FROM project_relevance_cte
	),

-- For each project/search/owner combination, we pick the one with the best distance.
non_default_owners
AS ( -- This CTE identifies sales person assignments with closest branch.
	SELECT b.*,
		sp._ownerid_value AS sales_rep_id
	FROM batch_upsert_leads b
	INNER JOIN `{data_set}.{sales_profile_temp}` sp 
        ON ( b.search_id = sp._fbm_searchid_value AND b.territory_id = sp._fbm_branchid_value ) -- territory-specific reps
            -- non-territory reps
            -- Assign if project HAS territory
        OR ( b.search_id = sp._fbm_searchid_value AND sp._fbm_branchid_value IS NULL AND b.territory_id  IS NOT NULL) 
        Qualify ROW_NUMBER() OVER (
			PARTITION BY b.project_id,
			b.search_id,
			sp._ownerid_value -- Partition by the specific owner to allow multiple owners per project
			ORDER BY b.distance ASC
			) = 1
	),
-- Assign default rep if no specific reps found for projects, find the closet branch to assign the default owner to.
default_owners_needed
AS (
	SELECT b.*,
		'{default_sales_rep_id}' AS sales_rep_id
	FROM batch_upsert_leads b
	LEFT JOIN non_default_owners ndo ON b.project_id = ndo.project_id
		AND b.search_id = ndo.search_id
	WHERE
		-- If ndo.project_id IS NULL, it means no match was found.
		-- These are the rows that need a default owner.
		ndo.project_id IS NULL
		-- For these fallback projects, we only want the single best row based on distance.
		Qualify ROW_NUMBER() OVER (
			PARTITION BY b.project_id,
			b.search_id ORDER BY b.distance ASC
			) = 1
	)
-- Combine the results of non-default owners and default owners.
SELECT  * FROM non_default_owners
UNION ALL
SELECT  * FROM default_owners_needed
"""