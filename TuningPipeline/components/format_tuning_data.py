import kfp
from kfp.dsl import component, Output, Dataset, Input
from kfp.compiler import Compiler
from typing import List 
import argparse
from typing import NamedTuple

def get_base_image():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base_image', type=str)
    args, _ = parser.parse_known_args()
    return args.base_image

@component(base_image=get_base_image(), install_kfp_package=False)
def format_tuning_data(project_id: str,
                bucket: str,
                uuid: str,
                
                # Prompt and parameters
                prompt: str,
                id_col: str,
                search_id_col: str, 
                search_name_col: str,
                query_col: str,
                territory_id_col: str,
                materials_valuation_col: str, 

                # BigQuery sales recommender parameters
                bq_dataset: str, 
                territory_table: str, 
                search_product_map_table: str,
                cc_feed_table: str, 
                dodge_feed_table: str, 
                consolidated_projects_bq_table: str,

                # Sales data parameters
                sales_project_id: str, 
                sales_dataset: str, 
                sales_table: str,  
                customer_table: str, 

                X_train: Input[Dataset],
                y_train: Input[Dataset],
                X_valid: Input[Dataset],
                y_valid: Input[Dataset],
                X_test: Input[Dataset], 
                y_test: Input[Dataset],

                # Output parameters 
                output_filename: str,
                historical_days: int = 60,

                # Split parameters 
                ) -> NamedTuple('outputs', [('formatted_training_dataset_gcs_uri', str), 
                                            ('formatted_validation_dataset_gcs_uri', str), 
                                            ('formatted_testing_dataset_gcs_uri', str)]):

    import logging
    import pandas as pd 
    import json
    from google.cloud import bigquery
    from tqdm import tqdm
    from utils import upload_file_to_gcs, row_to_example_input
    import os
    import pandas_gbq

    def format_dataframe(X_df: pd.DataFrame, 
                         y_df: pd.DataFrame,
                         id_col: str, 
                         search_id_col: str,
                         search_name_col: str,
                         territory_id_col: str,
                         query_col: str,
                         materials_valuation_col: str,
                         territory_df: pd.DataFrame, 
                         products_df: pd.DataFrame,
                         client: bigquery.Client,
                         prompt: str, 
                         project_id: str, 
                         bq_dataset: str, 
                         cc_feed_table: str,
                         dodge_feed_table: str,
                         consolidated_primary_leads_view: str,
                         historical_sales_df: pd.DataFrame,
                         historical_days: int,
                         data_type: str,
                         ): 
        
        formatted_content = [] 
        for index, row in tqdm(X_df.iterrows(), total=X_df.shape[0], desc=f"Formatting {data_type} data"): 
            
            try: 
                primary_project_id = row[id_col]

                # Extract search information 
                search_id = row[search_id_col]
                search_name = row[search_name_col] 

                 # List of relevant product caetgories for this search using the mapping
                products = products_df[products_df['fbm_searchid'] == search_id]['fbm_productcatcode'].tolist()
                boolean_filter = row[query_col] 

                # Extract territory information
                territory_id = row[territory_id_col]
                territory_name = territory_df[territory_df['id'] == territory_id]['name'].values[0] if not territory_df[territory_df['id'] == territory_id].empty else None

                materials_valuation = row[materials_valuation_col]
                if isinstance(materials_valuation, str): 
                    try:
                        materials_valuation = json.loads(materials_valuation)
                    except json.JSONDecodeError:
                        logging.warning(f"Could not parse materials_valuation as JSON: {materials_valuation}")
                        materials_valuation = {"material": 0}
                
                total_valuation = 0.0 
                for _, valuation in materials_valuation.items():
                    if isinstance(valuation, (int, float)):
                        total_valuation += valuation

                materials_valuation = total_valuation 

                row = row.drop([id_col, 
                                search_id_col, 
                                search_name_col, 
                                territory_id_col, 
                                query_col, 
                                materials_valuation_col])
                try:
                    input_data_parts = row_to_example_input(client=client,
                                                            prompt=prompt,
                                                            project_data=json.dumps(row.to_dict()),
                                                            primary_project_id=primary_project_id, 
                                                            search_name=search_name, 
                                                            products=products, 
                                                            boolean_filter=boolean_filter, 
                                                            territory_name=territory_name,
                                                            project_id=project_id, 
                                                            dataset=bq_dataset,
                                                            cc_feed_table=cc_feed_table, 
                                                            dodge_feed_table=dodge_feed_table, 
                                                            consolidated_primary_leads_view=consolidated_primary_leads_view,
                                                            historical_sales_df=historical_sales_df,
                                                            historical_days=historical_days,
                                                            materials_valuation=materials_valuation)
                except Exception as e:
                    logging.error(f"Error converting input data to example input: {e}")
                    continue 
                
                if data_type == 'testing': 
                    
                    content_row = {"contents": [part['text'] for part in input_data_parts]}
                    formatted_content.append(content_row)

                else: 
                    # Format response as json
                    output_data_json = y_df.loc[index].to_json() 

                    # Construct content row
                    content_row = {"contents": []}
                    content_row["contents"].append({"role": "user", "parts": input_data_parts})
                    content_row["contents"].append({"role": "model", "parts": [{"text": output_data_json}]})

                    # Add record to formatted training data
                    formatted_content.append(content_row)

            except Exception as e:
                logging.error(f"Error formatting input data: {e}")
                continue 


        return formatted_content


    def fetch_historical_data(project_id: str, 
                            dataset: str, 
                            sales_table: str, 
                            customer_table: str, 
                            historical_days: int): 
        
        query = f"""with customer_info as (
            select 
                CUSTOMER_WID, 
                CUSTOMER_PHONE_NUMBER as phone_number, 
            from `{project_id}.{dataset}.{customer_table}` customer
            )
            select 
                GROSS_PROFIT_AMT as gross_profit,
                PRODUCT_PRIMARY_CAT_DESC as product_category,
                PRODUCT_PRIMARY_CAT_CODE as product_category_code,
                ORDER_LOCATION_DESC as location,
                ORDER_ID as order_id,
                phone_number,
            from `{project_id}.{dataset}.{sales_table}` sales 
            left join customer_info 
            on sales.CUSTOMER_DIM_CODE = CAST(customer_info.CUSTOMER_WID as string)
            WHERE sales.CREATED_TIMESTAMP >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL {historical_days} DAY)  
            and sales.PRODUCT_PRIMARY_CAT_CODE is not null 
            and sales.PRODUCT_PRIMARY_CAT_CODE != ''
            and sales.PRODUCT_PRIMARY_CAT_DESC is not null 
            and sales.PRODUCT_PRIMARY_CAT_DESC != ''
        """

        results = pandas_gbq.read_gbq(query, project_id=project_id, use_bqstorage_api=True)
        results = results.dropna(subset = ["product_category", "location", "gross_profit"])

        return results 

    client = bigquery.Client()

    # Load input datasets
    logging.info("Loading input datasets...")
    with open(X_train.path, 'r') as f:
        X_train = pd.read_csv(f)    
    
    with open(y_train.path, 'r') as f:
        y_train = pd.read_csv(f)

    with open(X_valid.path, 'r') as f:
        X_valid = pd.read_csv(f)

    with open(y_valid.path, 'r') as f:
        y_valid = pd.read_csv(f)

    with open(X_test.path, 'r') as f:
        X_test = pd.read_csv(f)     

    with open(y_test.path, 'r') as f:   
        y_test = pd.read_csv(f)

    # Get dataframe of territories from bigquery 
    logging.info("Fetching territories from BigQuery...")
    query = f"""select id, name from `{project_id}.{bq_dataset}.{territory_table}`"""
    territory_df = pandas_gbq.read_gbq(query, project_id=project_id)

    # Get products from bigquery 
    logging.info("Fetching search-products map from BigQuery...")
    query = f"""select fbm_searchid, fbm_productcatcode from `{project_id}.{bq_dataset}.{search_product_map_table}`"""
    products_df = pandas_gbq.read_gbq(query, project_id=project_id)
    products_df.dropna(inplace=True)

    # Fetch all sales data from BigQuery from the last `historical_days` days
    logging.info(f"Fetching historical sales data from BigQuery for the last {historical_days} days...")
    historical_sales_df = fetch_historical_data(project_id=sales_project_id,
                                                dataset=sales_dataset, 
                                                sales_table=sales_table,
                                                customer_table=customer_table,
                                                historical_days=historical_days)
    
    logging.info(f"Historical sales data fetched with {len(historical_sales_df)} records.")

    # Format training data
    logging.info("Formatting training data...")
    formatted_training_data = format_dataframe(X_train, 
                                                y_train, 
                                                id_col, 
                                                search_id_col,
                                                search_name_col,
                                                territory_id_col,
                                                query_col,
                                                materials_valuation_col,
                                                territory_df, 
                                                products_df,
                                                client,
                                                prompt, 
                                                project_id, 
                                                bq_dataset, 
                                                cc_feed_table,
                                                dodge_feed_table,   
                                                consolidated_projects_bq_table,
                                                historical_sales_df,
                                                historical_days,
                                                data_type='training')
    
    logging.info(f"Formatted {len(formatted_training_data)} training records.")

    # Format validation data
    logging.info("Formatting validation data...")
    formatted_validation_data = format_dataframe(X_valid,
                                                y_valid, 
                                                id_col, 
                                                search_id_col,
                                                search_name_col,
                                                territory_id_col,
                                                query_col,
                                                materials_valuation_col,
                                                territory_df, 
                                                products_df,
                                                client,
                                                prompt, 
                                                project_id, 
                                                bq_dataset, 
                                                cc_feed_table,
                                                dodge_feed_table,   
                                                consolidated_projects_bq_table,
                                                historical_sales_df,
                                                historical_days,
                                                data_type='validation')
    
    logging.info(f"Formatted {len(formatted_validation_data)} validation records.")

    logging.info("Formatting testing data...")
    formatted_testing_data = format_dataframe(X_test,
                                                y_test, 
                                                id_col, 
                                                search_id_col,
                                                search_name_col,
                                                territory_id_col,
                                                query_col,
                                                materials_valuation_col,
                                                territory_df, 
                                                products_df,
                                                client,
                                                prompt, 
                                                project_id, 
                                                bq_dataset, 
                                                cc_feed_table,
                                                dodge_feed_table,   
                                                consolidated_projects_bq_table,
                                                historical_sales_df,
                                                historical_days,
                                                data_type='testing')


    # Save JSONL training data to local path 
    os.makedirs("tmp", exist_ok=True)
    output_training_jsonl = f"{output_filename}/{uuid}/training.jsonl"
    output_validation_jsonl = f"{output_filename}/{uuid}/validation.jsonl"
    output_testing_jsonl = f"{output_filename}/{uuid}/testing.jsonl"
    tmp_training = 'tmp/formatted_training_data.jsonl'
    tmp_validation = 'tmp/formatted_validation_data.jsonl'
    tmp_testing = 'tmp/formatted_testing_data.jsonl'

    with open(tmp_training, 'w') as f:
        for record in formatted_training_data:
            f.write(json.dumps(record) + '\n')

    with open(tmp_validation, 'w') as f:
        for record in formatted_validation_data:
            f.write(json.dumps(record) + '\n')

    with open(tmp_testing, 'w') as f:
        for record in formatted_testing_data:
            f.write(json.dumps(record) + '\n')

    # Upload training/validation data to GCS
    try: 
        logging.info(f"Uploading file to bucket: {bucket} with filenames: {output_training_jsonl}, {output_validation_jsonl}, {output_testing_jsonl}")
        formatted_training_dataset_gcs_uri = upload_file_to_gcs(tmp_training, bucket, output_training_jsonl)
        formatted_validation_dataset_gcs_uri = upload_file_to_gcs(tmp_validation, bucket, output_validation_jsonl)
        formatted_testing_data_gcs_uri = upload_file_to_gcs(tmp_testing, bucket, output_testing_jsonl)
    except Exception as e:
        logging.error(f"Failed to upload file {output_filename} to GCS. Error: {str(e)}")
        raise

    logging.info(f"Formatted training dataset GCS URI: {formatted_training_dataset_gcs_uri}")
    logging.info(f"Formatted validation dataset GCS URI: {formatted_validation_dataset_gcs_uri}")
    logging.info(f"Formatted testing dataset GCS URI: {formatted_testing_data_gcs_uri}")

    logging.info("Constructing outputs...")
    outputs = NamedTuple('outputs', [('formatted_training_dataset_gcs_uri', str), 
                                     ('formatted_validation_dataset_gcs_uri', str),
                                     ('formatted_testing_dataset_gcs_uri', str)])
                                    
    return outputs(formatted_training_dataset_gcs_uri, formatted_validation_dataset_gcs_uri, formatted_testing_data_gcs_uri)

if __name__ == "__main__":
    Compiler().compile(format_tuning_data, package_path="format_tuning_data.yaml")