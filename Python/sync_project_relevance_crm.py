import argparse
import concurrent.futures
import json
import math
import os
import sys
import traceback
from datetime import datetime, timezone
from functools import lru_cache

import numpy as np
import pandas as pd  # +++ Added for DataFrame operations +++
from google.cloud import bigquery

# Add CloudFunction directory path (adjust if necessary)
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cloud_function_path = os.path.join(project_root, "CloudFunction")
if cloud_function_path not in sys.path:
    sys.path.append(cloud_function_path)

try:
    from config import get_settings
    from services import BigQueryManager, DynamicsManager
    from utils.common import get_secret
    from batch_upsert_leads import (
        get_unique_combinations, 
        get_existing_lead_data, 
        separate_update_insert,
        build_batch_insert_data,
        build_batch_update_data,
        get_state_name,
        create_core_rows)
except ImportError as e:
    print(f"Error importing shared modules: {e}")
    print(
        "Please ensure the CloudFunction directory is structured correctly and accessible."
    )
    raise

# --- Helper functions (get_dynamics_client, process_cc_row_data, get_unique_combinations, normalize_time_for_key) remain largely the same ---

def get_dynamics_client(project_number, dynamics_instance):
    """Initializes DynamicsManager using shared components."""
    try:
        dynamics_cred_json = get_secret(
            project_number=project_number, secret_name="dynamics_cred"
        )
        dynamics_cred = json.loads(dynamics_cred_json)
        tenant_id = dynamics_cred["TENANT_ID"]
        application_id = dynamics_cred["APPLICATION_ID"]
        client_secret = dynamics_cred["CLIENT_SECRET"]

        dynamics_client = DynamicsManager(
            domain=dynamics_instance,
            client_id=application_id,
            client_secret=client_secret,
        )
        
        try:
            # Ensure MSAL is available if needed directly
            import msal

            msal_app = msal.ConfidentialClientApplication(
                application_id,
                authority=f"https://login.microsoftonline.com/{tenant_id}",
                client_credential=client_secret,
            )
            token_result = msal_app.acquire_token_for_client(
                scopes=[f"{dynamics_instance}/.default"]
            )
            if "access_token" in token_result:
                dynamics_client.set_access_token(token_result["access_token"])
            else:
                print(f"Error acquiring token: {token_result.get('error_description')}")
                raise Exception("Failed to acquire Dynamics access token")
        except ImportError:
            print(
                "Warning: MSAL library not found. Assuming DynamicsManager handles auth internally."
            )
        except Exception as auth_e:
            print(f"Error during Dynamics authentication: {auth_e}")
            raise

        return dynamics_client
    except Exception as e:
        print(f"Error initializing Dynamics client: {e}")
        traceback.print_exc()
        raise


def get_cc_row(settings, start_row_no, end_row_no, bq_client):
    query = f"""
        -- Extract contacts
            WITH  project_relevance AS( 
                SELECT Project_ID,time_created
                FROM `{settings.BIGQUERY_DATASET}.sync_project_relevance`
                WHERE row_no between {start_row_no} and {end_row_no}
            ),
            exploded AS (
                SELECT
                    ProjectID,
                    company.CompanyID,
                    company.Name AS company_name,
                    company.BiddingRole,
                    company,
                    contact
                FROM (
                    SELECT
                        ProjectID,
                        Companies
                    FROM
                        `{settings.BIGQUERY_DATASET}.{settings.CC_FEED_TABLE_ID}`
                    INNER JOIN project_relevance  pr
                    ON pr.time_created = sourceFileCreationTime
                        AND pr.project_id = ProjectID
                ),
                UNNEST(Companies) AS company_wrap,
                UNNEST(company_wrap.Company) AS company,
                UNNEST(company.contacts.contact) AS contact
            ),
            gc_contact AS (
                select  ProjectID ,
                    LEFT(company.name, 50) AS companyname,
                    LEFT(company.Addresses.Address[SAFE_OFFSET(0)].City, 50) AS address1_city,
                    LEFT(company.Addresses.Address[SAFE_OFFSET(0)].StateProvince, 50) AS address1_stateorprovince,
                    LEFT(company.Addresses.Address[SAFE_OFFSET(0)].County, 50) AS address1_county,
                    LEFT(company.Email, 50) AS emailaddress1,
                    (
                        SELECT ph.PhoneNumnber
                        FROM UNNEST(company.Phones.phone) AS ph
                        WHERE ph.PhoneType = 'Company Phone Number'
                    ) AS mobilephone,
                    LEFT(SPLIT(company.Contacts.Contact[SAFE_OFFSET(0)].Name, ' ')[SAFE_OFFSET(0)], 50) AS firstname,
                    LEFT(SPLIT(company.Contacts.Contact[SAFE_OFFSET(0)].Name, ' ')[SAFE_OFFSET(1)], 50) AS lastname
                from exploded
                where BiddingRole = "General Contractor"
                qualify ROW_number() OVER(PARTITION BY ProjectID ) =1
            ),
            -- Convert contact struct to JSON strings
            contact_jsons AS (
                SELECT
                    ProjectID,
                    CompanyID,
                    CASE
                        WHEN BiddingRole = "General Contractor" THEN FORMAT(
                            '{{"Company Name":"%s","Name":%s,"Email":%s,"PhoneNumber":%s}}',
                            company_name,
                            IF(contact.Name IS NULL, 'null', FORMAT('"%s"', contact.Name)),
                            IF(contact.Email IS NULL, 'null', FORMAT('"%s"', contact.Email)),
                            IF(contact.PhoneNumber IS NULL, 'null', FORMAT('"%s"', contact.PhoneNumber))
                        )
                        ELSE NULL
                    END AS contact_json
                FROM
                    exploded
            ),
            -- Group back into comma-separated contact string
            contact_group AS (
                SELECT
                    ProjectID,
                    CompanyID,
                    STRING_AGG(contact_json, ',') AS contact
                FROM
                    contact_jsons
                GROUP BY
                    ProjectID,
                    CompanyID
            ),
            bidder_group AS (
                SELECT
                    ProjectID,
                    STRING_AGG(contact, '\\n') AS bidder_lead_list
                FROM
                    contact_group
                GROUP BY
                    ProjectID
            )
            SELECT
                cc.*,
                gc_contact.* except(ProjectID),
                bidder_lead_list AS fbm_externalleadbidders
            FROM (
                SELECT
                    ProjectID AS fbm_externalleadid,
                    Title AS arb_project_name,
                    Stage AS fbm_projectstage,
                    Parameters_Parameter_BidDate AS fbm_biddate,
                    Valuation_Value AS estimatedamount,
                    Parameters_Parameter_CommenceDate AS fbm_startdate,
                    sourceFileCreationTime AS fbm_lastsyncdate,

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
                    --Parameters_Parameter_FloorAreaUnitofMeasure AS LeadSquareFootageUnit -- Adjusted alias slightly to match previous version for consistency
                                
                FROM
                    `{settings.BIGQUERY_DATASET}.{settings.CC_FEED_TABLE_ID}`
                INNER JOIN project_relevance  pr
                ON pr.time_created = sourceFileCreationTime
                    AND pr.project_id = ProjectID
            ) cc
            LEFT JOIN   bidder_group
                ON  cc.fbm_externalleadid = bidder_group.ProjectID
            LEFT JOIN   gc_contact
                ON  cc.fbm_externalleadid = gc_contact.ProjectID;
                """
    result = bq_client.query_table(query=query)

    cc_data_dict = {}
    for row in result:
        row = dict(row)
        row["fbm_externalleadid"] = str(row["fbm_externalleadid"])
        row["estimatedamount"] = (
            float(row["estimatedamount"]) if row["estimatedamount"] else None
        )
        row["fbm_projectdescription"] = row["fbm_projectdescription"][:2000]
        cc_data_dict[int(row["fbm_externalleadid"])] = dict(row)

    return cc_data_dict



# --- Main function updated ---
def main(
    project_number,
    dynamics_instance,
    pr_batch_size
):

    settings = get_settings()  # Initialize settings early

    try:
        dynamics_client = get_dynamics_client(project_number, dynamics_instance)
    except Exception as e:
        print(f"FATAL: Failed to initialize Dynamics Client. Exiting. Error: {e}")
        return

    try:
        big_query_client = BigQueryManager(dataset_id=settings.BIGQUERY_DATASET)
    except Exception as e:
        print(f"FATAL: Failed to initialize BigQuery Client. Exiting. Error: {e}")
        return

    # 1. Get project_relevance (deduplicated by latest modified_on per P/S.)
    # 2. Excluding projects whose search_id no longer exists in the fbm_searches table in CRM.
    print("Fetching project relevance data...")
    relevance_query = f"""
        CREATE OR REPLACE TABLE `{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.sync_project_relevance` AS
        SELECT 
            ROW_NUMBER() OVER (ORDER BY project_id, search_id, territory_id) AS row_no,
            *
        FROM (
            SELECT project_relevance.*
            FROM `{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.{settings.PROJECT_RELEVANCE_TABLE_ID}` project_relevance
            INNER JOIN `proj-sales-recommender-dev.sales_recommender_dev.searches` searches
                ON project_relevance.search_id = searches.id
            QUALIFY ROW_NUMBER() OVER (PARTITION BY project_id, search_id ORDER BY distance ASC, modified_on DESC) = 1
        )
        ORDER BY 1;
        """
    
    big_query_client.query_table(query=relevance_query)
    
    # Getting the total number of projects to be synced
    query = f"SELECT MAX(row_no) AS row_count FROM `{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.sync_project_relevance`"
    result = big_query_client.query_table(query=query)
    project_relevance_count = result[0]['row_count']

    
    # Syncing projects in chunks
    batch_cnt = 1
    for start_row_no in range(1, project_relevance_count + 1, pr_batch_size):
        end_row_no = min(start_row_no + pr_batch_size - 1, project_relevance_count)
        print(f"Batch-{batch_cnt}: project sync started...")
        print(start_row_no,end_row_no)
        query = f"""
            SELECT pr.*
            FROM `{settings.BIGQUERY_DATASET}.sync_project_relevance` pr
            WHERE row_no between {start_row_no} and {end_row_no}
            """
        result = big_query_client.query_table(query=query, to_dataframe=True)

        # Add core rows to the result
        core_df = create_core_rows(result, settings)
        result = pd.concat([result, core_df], ignore_index=True)

        # Replace NaN values with None
        result = result.replace({np.nan: None})

        project_relevance_data = result.to_dict(orient="records")
        
        project_relevance_data_map = {}
        for row in project_relevance_data:
            key = (row["project_id"], row["search_id"])
            project_relevance_data_map[key] = row
        
        cc_data_index = get_cc_row(
            settings=settings,
            start_row_no=start_row_no,
            end_row_no=end_row_no,
            bq_client=big_query_client,
        )

        unique_combinations = get_unique_combinations(
            settings, dynamics_client, project_relevance_data
        )

        already_exists_leads = {}
        # Fetching in chunks because the GET request is failing due to a URI being too long.
        leads_query_size = 100
        if len(unique_combinations) > 0:
            for i in range(0, len(unique_combinations), leads_query_size):
                chunk = unique_combinations[i : i + leads_query_size]
                already_exists_leads |= get_existing_lead_data(
                    dynamics_client, chunk, settings
                )

        insert_leads, update_leads = separate_update_insert(
            already_exists_leads, unique_combinations, cc_data_index
        )
        update_batch_data = build_batch_update_data(
            update_leads, project_relevance_data_map
        )
        insert_batch_data = build_batch_insert_data(
            insert_leads, project_relevance_data_map
        )

        log_message=f"Batch-{batch_cnt} : insert leads: {len(insert_leads)} , already exists leads: {len(update_leads)} and update leads: {len(update_batch_data)}"
        print(log_message)

        batch_size = 100
        # loading data in chucks due to limitation of CRM batch api
        if len(insert_batch_data) > 0:
            # Executing 10 concurrent batch inserts to reduce overall execution time.
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=10
            ) as executor:
                for i in range(0, len(insert_batch_data), batch_size):
                    chunk = insert_batch_data[i : i + batch_size]
                    future = executor.submit(
                        dynamics_client.send_batch_create,
                        chunk,
                        f"{settings.DM_LEAD_ID}s"
                    )

        

        # Updating data in chucks due to limitation of CRM batch api            
        if len(update_batch_data) > 0:
            # Executing 10 concurrent batch update to reduce overall execution time.
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=10
            ) as executor:
                for i in range(0, len(update_batch_data), batch_size):
                    
                    chunk = update_batch_data[i : i + batch_size]
                    future = executor.submit(
                        dynamics_client.send_batch_update,
                        chunk,
                        f"{settings.DM_LEAD_ID}s",
                        "leadid"
                    )  

        batch_cnt+=1
    
    query = f"DROP TABLE {settings.BIGQUERY_DATASET}.sync_project_relevance;"
    big_query_client.query_table(query=query)



# --- __main__ block remains the same ---
if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Sync project relevance data from BigQuery to Dynamics CRM, assigning to the closest rep."
    )
    parser.add_argument(
        "--dynamics_instance",
        type=str,
        default="https://fbmsales-sandbox.api.crm.dynamics.com",
        help="Dynamics CRM instance URL",
    )
    parser.add_argument(
        "--project_number",
        type=str,
        default="195063057478",
        help="GCP Project Number (for secrets)",
    )
    parser.add_argument(
        "--pr_batch_size",
        type=int,
        default=2000,
        help="BigQuery Dataset ID",
    )
  

    args = parser.parse_args()

    print("Starting CRM sync process with minimum distance logic...")

    main(
        args.project_number,
        args.dynamics_instance,
        args.pr_batch_size
    )
    print("CRM sync process finished.")