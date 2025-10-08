import kfp
from kfp.dsl import component, Output, Dataset
from kfp.compiler import Compiler
import argparse
from typing import NamedTuple, List

def get_base_image():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base_image', type=str)
    args, _ = parser.parse_known_args()
    return args.base_image

@component(base_image=get_base_image(), install_kfp_package=False)
def ingest_data(project_id: str, 
                location: str,
                dm_instance_url: str,
                bq_dataset: str,
                id_col: str,
                search_id_col: str, 
                search_name_col: str,
                query_col: str,
                territory_id_col: str, 
                territory_distance_col: str,
                materials_valuation_col: str,
                response_col: str,
                boolean_filters_bq_table: str,
                ranking_cols_bq_table: str,
                coalesced_projects_bq_table: str,
                dataset: Output[Dataset], 
                is_testing: bool = False, 
                ) -> NamedTuple('outputs', [('ranking_columns', List[str])]):
    
    import logging
    import json
    from utils import setup_logging, init_vertex, access_secret_version, download_file_from_gcs
    import pandas as pd
    import pandas_gbq
    from dynamics_manager import DynamicsManager
    import numpy as np

    def create_dynamics_client(project_id, dm_instance_url): 
        try: 
            # Fetch credentials from Secret Manager
            dynamics_cred = access_secret_version(project_id=project_id, secret_id="dynamics_cred")
            dynamics_cred = json.loads(dynamics_cred)

            logging.info("Fetched credentials from Secret Manager.")
            application_id = dynamics_cred['APPLICATION_ID']
            client_secret = dynamics_cred['CLIENT_SECRET']
            tenant_id = dynamics_cred['TENANT_ID']
            dynamics_instance = dm_instance_url
            resource = f"{dynamics_instance}/"

            # Create DynamicsManager client
            dynamics_client = DynamicsManager(domain=dynamics_instance, client_id=application_id, client_secret=client_secret)
            result = dynamics_client.build_msal_client(tenant_id).acquire_token_for_client([f"{resource}.default"])
            dynamics_client.set_access_token(result['access_token'])

            return dynamics_client

        except Exception as e:
            logging.error(f"Error fetching credentials: {e}")
            raise

    lead_statecode_mapping = {
        0: 'open',
        1: 'qualified',
        2: 'disqualified'
    }

    lead_statuscode_mapping = {
        866070005: 'Out of Territory',
        866070006: '"Out of Scope / Not a Fit"',
        866070007: 'Bad or Incomplete Data',
        866070004: 'Already Managed / Duplicate',
        5: 'Not Interested / No Response',
        7: 'Other',
    }

    relevance_code_mapping = {
        866070000: 'Very High',
        866070001: 'High',
        866070002: 'Moderate',
        866070003: 'Low',
        866070004: 'Very Low',
        866070005: 'Unsure',
        866070006: 'Not Relevant',
    }

    setup_logging()
    init_vertex(project_id, location)

    # Set up client for reading data from CRM tables
    logging.info("Setting up DynamicsManager client...")
    dynamics_client = create_dynamics_client(project_id, dm_instance_url)

    # Fetch Search table from BigQuery
    # columns = {'id': str, 'name': str, 'boolean': str}
    logging.info("Fetching Search table from BigQuery...")
    searches_df = pandas_gbq.read_gbq(f"""select id, name, boolean from `{project_id}.{bq_dataset}.{boolean_filters_bq_table}`""", 
                                            project_id=project_id)
    searches_df.rename({'id': search_id_col, 'name': search_name_col, 'boolean': query_col}, axis=1, inplace=True)
    
    logging.info("Fetching ranking columns from BigQuery...")
    ranking_cols_df = pandas_gbq.read_gbq(f"""select * from `{project_id}.{bq_dataset}.{ranking_cols_bq_table}`""", 
                                            project_id=project_id)
    
    ranking_cols = ranking_cols_df['name'].tolist()
    if id_col in ranking_cols:
        ranking_cols.remove(id_col)
    
    # Fetch data from leads table
    logging.info("Fetching data from leads table...")
    leads_df = pd.DataFrame(dynamics_client.get_data("leads")['value'])

    # # Fetch relevant columns from Leads 
    leads_df = leads_df[['fbm_externalleadid', 
                        '_fbm_searchid_value', 
                        '_fbm_branch_value', 
                        'fbm_distance',
                        '_ownerid_value',
                        'statecode', 
                        'statuscode',
                        'fbm_relevance', 
                        'leadid']]
    
    # Map statecode values to project state - open, qualified, or disqualified 
    leads_df['statecode'] = leads_df['statecode'].map(lead_statecode_mapping)
    # Map statuscode value to reason for disqualification
    leads_df['statuscode'] = leads_df['statuscode'].map(lead_statuscode_mapping)
    # Map fbm_relevance to relevance label 
    leads_df['fbm_relevance'] = leads_df['fbm_relevance'].map(relevance_code_mapping)

    # Rename columns
    leads_df.rename({'fbm_externalleadid': id_col, 
                    '_fbm_searchid_value': search_id_col, 
                    '_fbm_branch_value': territory_id_col,
                    'fbm_distance': territory_distance_col,
                    'statecode': 'lead_statecode', 
                    'statuscode': 'lead_statuscode', 
                    'fbm_relevance': response_col}, axis=1, inplace=True)
    
    # Merge search ID, name, filter to leads 
    logging.info("Adding searches to leads data...")
    leads_df = leads_df.merge(searches_df, how='left', on=search_id_col)
    logging.info("Leads data columns: %s", leads_df.columns.tolist())

    # Fetch data from sales profile table 
    logging.info("Fetching data from sales profile table...")
    sales_profile_df = pd.DataFrame(dynamics_client.get_data('fbm_salesprofiles')['value'])

    # Fetch relevant columns from sales profile
    sales_profile_df = sales_profile_df[['_ownerid_value', 
                                        '_fbm_searchid_value', 
                                        '_fbm_branchid_value', 
                                        'fbm_allowfeedback']]
    # Rename columns
    sales_profile_df.rename({'_fbm_searchid_value': search_id_col, 
                                      '_fbm_branchid_value': territory_id_col}, axis=1, inplace=True)
    logging.info("Sales data columns: %s", sales_profile_df.columns.tolist())

    # Merge sales profile with leads
    leads_df_allow_feedback = leads_df.merge(sales_profile_df, how='left', on=['_ownerid_value', search_id_col, territory_id_col])

    # Only use examples if fbm_allowfeedback is True on the salesperson, search, and branch level
    logging.info("Filtering leads where feedback is allowed...")
    leads_df_allow_feedback = leads_df_allow_feedback[leads_df_allow_feedback['fbm_allowfeedback'] == True]

    # Add materials_valuation to leads 
    logging.info("Adding materials valuation to leads...")
    branch_opps_df = pd.DataFrame(dynamics_client.get_data('fbm_branchopportunities')['value'])
    branch_opps_df_relevant = branch_opps_df[['fbm_branchopportunityid', 'fbm_estimatedrevenue', '_fbm_productcategoryid_value']]

    # Convert rows of category and revenue to dictionary 
    valuation_df = branch_opps_df_relevant.groupby('fbm_branchopportunityid').agg({
        '_fbm_productcategoryid_value': list, 
        'fbm_estimatedrevenue': list
        }).apply(lambda x: dict(zip(x['_fbm_productcategoryid_value'], x['fbm_estimatedrevenue'])), 
        axis = 1).reset_index()

    valuation_df.columns = ['leadid', materials_valuation_col]
    leads_df_allow_feedback = leads_df_allow_feedback.merge(valuation_df, how='left', on='leadid')
    leads_df_allow_feedback.fillna({materials_valuation_col: {}}, inplace=True)

    # Construct responses allowed for feedback
    logging.info("Constructing responses with valuation...")
    response_df = leads_df_allow_feedback[[id_col, search_id_col, search_name_col, query_col, 
                                           territory_id_col, territory_distance_col, 'lead_statecode', 'lead_statuscode', 
                                           materials_valuation_col, response_col]]

    # Filter out open leads
    response_df = response_df[response_df['lead_statecode'].isin(['disqualified', 'qualified'])] 
    # Drop rows with missing project/search/response
    response_df.dropna(subset=[id_col, search_id_col, response_col], inplace=True) 
    logging.info("Response data columns: %s", response_df.columns.tolist())
    logging.info(f"Response: {response_df.head()}")

    if response_df.empty:
        raise ValueError("No data found where feedback is allowed.")
    
    def map_status_to_relevance(row): 
        # Qualified leads turned into opportunities - keep same relevance
        if row['lead_statecode'] == 'qualified': 
            return row[response_col]
        # Disqualified leads - map to relevance based on reason for disqualification
        elif row['lead_statecode'] == 'disqualified':
            statuscode = row['lead_statuscode']
            # Reasons for low relevance
            if "out of scope" or "out of territory" or "not a fit" or "bad or incomplete data" in statuscode.lower():
                return 'Low'
            # Reasons which have no impact on relevance
            elif "already managed" or "duplicate" or "not interested" or "no response" or "other" in statuscode.lower():
                return row['lead_statuscode']

    # Apply mapping to response_df
    logging.info("Mapping lead status to relevance...")
    response_df[response_col] = response_df.apply(map_status_to_relevance, axis=1)
    response_df = response_df[[id_col, search_id_col, search_name_col, query_col, territory_id_col, 
                               territory_distance_col, materials_valuation_col, response_col]]

    # Fetch project IDs from response_df
    project_ids = response_df[id_col].dropna().unique()
    projects_str = '"' + '", "'.join(project_ids) + '"'
    logging.info(f"Fetched leads: {projects_str}")

    query_coalesced_projects = f"""
    SELECT * FROM `{project_id}.{bq_dataset}.{coalesced_projects_bq_table}` 
    WHERE ProjectID IN UNNEST([{projects_str}]) 
    """

    print(query_coalesced_projects)

    # Fetch coalesced projects from BigQuery
    logging.info("Fetching coalesced project data from BigQuery...")
    coalesced_projects_df = pandas_gbq.read_gbq(query_coalesced_projects, 
                                                project_id=project_id)

    # Merge coalesced projects with response_df 
    response_df = coalesced_projects_df.merge(response_df, how='left', on=id_col)
    logging.info("Project data added to response dataframe.")
    logging.info(f"Number of projects: {len(response_df)}")
    
    logging.info(f"Response: {response_df.head()}")

    response_df.to_csv(dataset.path, index = False) # Save to output path

    # Check if we're in testing mode
    if is_testing:

        # Fetch already labeled data 
        bucket = 'sales_recommender_dev_bucket'
        blob = 'data/cc_classification_sample_with_distance_materials_valuation.csv'

        local_file = 'responses.csv'
        download_file_from_gcs(bucket, blob, local_file)
        result = pd.read_csv(local_file)
        logging.info(f"Data frame downloaded from GCS: {result.head()}")
        result[id_col] = result[id_col].astype(str)
        # Create materials valuation as dictionary with "material" key and random int value
        materials_valuations = []
        for _ in range(len(result)):
            material_dict = {"material": np.random.randint(1000, 100000)}
            material_dict = json.dumps(material_dict)
            materials_valuations.append(material_dict)
            
        result[materials_valuation_col] = materials_valuations

        result = result.sample(n=20)

        result.to_csv(dataset.path, index=False)
    
    # --- end sample for testing --- 

    outputs = NamedTuple('outputs', [('ranking_columns', List[str])])
    return outputs(ranking_cols)              

if __name__ == "__main__":
    Compiler().compile(ingest_data, package_path="ingest_data.yaml")