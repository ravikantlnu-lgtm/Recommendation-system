from google.cloud import bigquery  
import pandas as pd 
import numpy as np
import json 
import argparse
import os

# Global paths
DATA_DIR = "tests/data"
os.makedirs(DATA_DIR, exist_ok=True)
BOOLEAN_FILTERS_PATH = os.path.join(DATA_DIR, "boolean_filters.csv")
TERRITORIES_PATH = os.path.join(DATA_DIR, "territories.csv")

# preprocess_data.py: Input dataset 
UNPROCESSED_DATA_PATH = os.path.join(DATA_DIR, "unprocessed_data.csv") # Input for preprocess_data.py

# Used for further data handling
PREPROCESSED_DATA_PATH = os.path.join(DATA_DIR, "preprocessed_data.csv") # Input for split_data.py

# split_data.py: Input datasets 
SAMPLE_DATA_PATH = os.path.join(DATA_DIR, "sample_data.csv")    
SAMPLE_POOL_PATH = os.path.join(DATA_DIR, "sample_pool.csv")

# format_tuning_data.py: Input datasets 
X_TRAIN_PATH = os.path.join(DATA_DIR, "X_train.csv")
Y_TRAIN_PATH = os.path.join(DATA_DIR, "y_train.csv")
X_VALID_PATH = os.path.join(DATA_DIR, "X_valid.csv")
Y_VALID_PATH = os.path.join(DATA_DIR, "y_valid.csv")
X_TEST_PATH = os.path.join(DATA_DIR, "X_test.csv")
Y_TEST_PATH = os.path.join(DATA_DIR, "y_test.csv")

# Fetch and save boolean filters from BigQuery
def fetch_boolean_filters(client, project_id, bq_dataset, searches_table): 
    query = f"""select id, name, boolean from {project_id}.{bq_dataset}.{searches_table}""" 
    result = client.query(query).to_dataframe() 
    result.to_csv(BOOLEAN_FILTERS_PATH, index=False)

# Fetch and save territories from BigQuery
def fetch_territories(client, project_id, bq_dataset, territories_table): 
    query = f"""select id, name from {project_id}.{bq_dataset}.{territories_table}""" 
    result = client.query(query).to_dataframe() 
    result.to_csv(TERRITORIES_PATH, index=False)

# Create response data for the tuning pipeline 
# Fetches random coalesced projects and assigns random searches, territories, and materials valuation
# Saves preprocessed data and unprocessed data
def create_response_data(client, 
                         project_id, 
                         bq_dataset, 
                         coalesced_projects_df,
                         search_id_col, 
                         search_name_col, 
                         query_col, 
                         territory_id_col, 
                         territory_distance_col,
                         materials_valuation_col, 
                         response_col, 
                         number_examples=20): 

    # Fetch coalesced projects from BigQuery
    query = f"""select * from `{project_id}.{bq_dataset}.{coalesced_projects_df}`
                limit {number_examples}"""
    result = client.query(query).to_dataframe()

    # Fetch saved boolean filters
    boolean_searches = pd.read_csv(BOOLEAN_FILTERS_PATH)    

    # Fetch saved territories
    territories = pd.read_csv(TERRITORIES_PATH)

    # Create labels
    labels =["Very High", "High", "Moderate", "Low", "Very Low", "Not Relevant"]
    
    random_filters = boolean_searches.sample(n=len(result), replace=True).reset_index(drop=True) 

    # Assign random searches, territories, and materials valuation
    result[search_id_col] = random_filters['id']
    result[search_name_col] = random_filters['name']
    result[query_col] = random_filters['boolean'] 

    result[territory_id_col] = np.random.choice(territories['id'], size=len(result))
    result[territory_distance_col] = np.random.randint(1, 100)
    
    # Create materials valuation as dictionary with "material" key and random int value
    materials_valuations = []
    for _ in range(len(result)):
        material_dict = {"material": np.random.randint(1000, 100000)}
        material_dict = json.dumps(material_dict)
        materials_valuations.append(material_dict)
        
    result[materials_valuation_col] = materials_valuations
    
    result[response_col] = np.random.choice(labels, size=len(result))

    # Save preprocessed data
    result.to_csv(PREPROCESSED_DATA_PATH, index=False)

    # Create unprocessed data
    unprocessed_df = result.copy() 
    # Remove search_id_col from a row of data 
    result.iloc[0][search_id_col] = None
    unprocessed_df.to_csv(UNPROCESSED_DATA_PATH, index=False)

# Create sample and pool data for split_data.py from preprocessed data
def create_sample_and_pool_df(pool_size = .10): 
    # Read preprocessed data
    df = pd.read_csv(PREPROCESSED_DATA_PATH)

    # Create sample and pool data
    df_sample = df.sample(frac=1-pool_size)
    df_pool = df.drop(df_sample.index)

    # Save sample and pool data
    df_sample.to_csv(SAMPLE_DATA_PATH, index=False)
    df_pool.to_csv(SAMPLE_POOL_PATH, index=False)

# Create split data for format_tuning_data.py
def create_split_data_df(id_col, search_id_col, territory_id_col, response_col):
    
    df = pd.read_csv(PREPROCESSED_DATA_PATH)

    # Split data into train, valid, and test sets
    df_train = df.sample(frac=0.8, random_state=42)
    df_valid = df_train.sample(frac=0.1, random_state=42)
    df_test = df.drop(df_train.index)
    
    # Create X and y data for format_tuning_data.py
    X_train = df_train.drop(columns=[response_col])
    y_train = df_train[[id_col, search_id_col, territory_id_col, response_col]]
    X_valid = df_valid.drop(columns=[response_col])
    y_valid = df_valid[[id_col, search_id_col, territory_id_col, response_col]]
    X_test = df_test.drop(columns=[response_col])
    y_test = df_test[[id_col, search_id_col, territory_id_col, response_col]]

    # Save X and y data for format_tuning_data.py
    X_train.to_csv(X_TRAIN_PATH, index=False)

    print(X_train.head())
    y_train.to_csv(Y_TRAIN_PATH, index=False)
    X_valid.to_csv(X_VALID_PATH, index=False)           
    y_valid.to_csv(Y_VALID_PATH, index=False)
    X_test.to_csv(X_TEST_PATH, index=False)           
    y_test.to_csv(Y_TEST_PATH, index=False)


if __name__ == "__main__": 

    os.makedirs(DATA_DIR, exist_ok=True)
    
    argparser = argparse.ArgumentParser(description="Create test data for sales recommender")
    argparser.add_argument("-c", "--config", type=str, required=True, help="configuration file")
    argparser.add_argument("-n", "--num_examples", type=int, required=True) 
    args = argparser.parse_args()

    config_path = args.config
    with open(config_path, "r") as config_file:
        config = json.load(config_file)

    client = bigquery.Client() 

    project_id = config["project_id"]
    bq_dataset = config["bq_dataset"]
    searches_table = config["boolean_filters_bq_table"]
    territories_table = config["territories_bq_table"]
    coalesced_projects_df = config["coalesced_projects_bq_table"]
    id_col = config["id_col"]
    search_id_col = config["search_id_col"]
    search_name_col = config["search_name_col"]
    query_col = config["query_col"]
    territory_id_col = config["territory_id_col"]
    territory_distance_col = config["territory_distance_col"]
    materials_valuation_col = config["materials_valuation_col"]
    response_col = config["response_col"]

    fetch_boolean_filters(client, project_id, bq_dataset, searches_table)

    fetch_territories(client, project_id, bq_dataset, territories_table)
    
    create_response_data(client, 
                         project_id, 
                         bq_dataset, 
                         coalesced_projects_df, 
                         search_id_col, 
                         search_name_col, 
                         query_col, 
                         territory_id_col, 
                         territory_distance_col,
                         materials_valuation_col, 
                         response_col, 
                         number_examples=int(args.num_examples))
    
    create_sample_and_pool_df()

    create_split_data_df(id_col, search_id_col, territory_id_col, response_col)