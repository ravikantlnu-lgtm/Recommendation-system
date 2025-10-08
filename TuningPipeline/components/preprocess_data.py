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
def preprocess_data(project_id: str, 
                    bucket: str, 
                    uuid: str,
                    id_col: str, 
                    search_id_col: str, 
                    search_name_col: str, 
                    query_col: str,
                    territory_id_col: str, 
                    territory_distance_col: str, 
                    materials_valuation_col: str, 
                    response_col: str, 
                    ranking_cols: List[str],
                    dataset: Input[Dataset],
                    max_diff: float,
                    output_filename: str,
                    max_sample_size: int = 1000,
                    clustering: bool = False,
                    clustering_inf: dict = None, 
                    column_types: dict = None,
                    sentence_transformer_name: str = "all-MiniLM-L6-v2",
                    random_state: int = 42
                    ) -> NamedTuple('outputs', [('dataset_gcs_uri', str), ('pool_gcs_uri', str)]):
    
    import pandas as pd 
    import numpy as np
    import logging
    import ast
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    import os
    from utils import upload_file_to_gcs, encode_df_for_clustering

    def assign_valuation_bucket(value: float) -> str: 
        try:
            if value >= 100000000:
                return ">100M"
            elif 50000000 <= value < 100000000:
                return "50M-100M"
            elif 25000000 <= value < 50000000:
                return "25M-50M"
            elif 10000000 <= value < 25000000:
                return "10M-25M"
            elif 5000000 <= value < 10000000:
                return "5M-10M"
            elif 2000000 <= value < 5000000:
                return "2M-5M"
            elif 1000000 <= value < 2000000:
                return "1M-2M"
            else:
                return "Under 1M"
        except (ValueError, AttributeError):
            return "Invalid Value"

    def safe_eval(address):
        try:
            # Replace 'Decimal' with 'float' to handle unsupported types
            address = address.replace("Decimal(", "").replace(")", "")
            # Evaluate the string safely
            return ast.literal_eval(address)
        except (ValueError, SyntaxError):
            return None
                
    def generate_column_proportions(df: pd.DataFrame, cols_to_check: List[str], label: str) -> dict: 
        """
        This function generates the proportion of each column values in the dataframe.

        Args:
            df (pd.DataFrame): The dataframe to analyze.
            cols_to_check (list): A list of column names to check.
            label (str): A label to append to the column names in the output.
        Returns:
            proportions_dict (dict): A dictionary containing the proportions of each column values.
        """

        proportions_dict = {} 

        # Generate value counts for each column
        for col in cols_to_check: 
            # Extract proportion of each state
            if col == 'State':
                # Fetch state from address
                try: 
                    df['State'] = df['Addresses_Address'].apply(lambda x: x[0]['StateProvince']) 

                except Exception as e: 
                    logging.error(f"Error extracting state from address: {e}")
                    logging.info("Attempting to extract state from address using safe_eval...")
                    try: 
                        df['State'] = df['Addresses_Address'].apply(
                            lambda x: safe_eval(x)[0]['StateProvince'] if x else None) 
                    except Exception as e:
                        logging.error(f"Error extracting state from address using safe_eval: {e}")
                        raise 
                    
                state_counts = df['State'].value_counts(normalize=True) 
                # Add to value counts df
                proportions_dict[f"{col}_{label}"] = pd.DataFrame(state_counts).reset_index()
                proportions_dict[f"{col}_{label}"].columns = [col, 'Proportion'] 
            else: 
                col_counts = df[col].value_counts(normalize=True) 
                proportions_dict[f"{col}_{label}"] = pd.DataFrame(col_counts).reset_index()
                proportions_dict[f"{col}_{label}"].columns = [col, 'Proportion']
        
        return proportions_dict

    def check_distribution_is_within_historical_data(historical_df: pd.DataFrame,
                                            df: pd.DataFrame, max_diff: float = 0.2) -> bool:
        
        """
        This function calcuates the distribtion of key columns in the current data and compares it to the historical data.
        It checks if the distribution of key columns is within a specified maximum difference.
        Args:
            historical_data (str): The historical dataframe. 
            df (pd.DataFrame): The current dataframe to analyze.
            max_diff (float): The maximum allowed difference in proportions.
        Returns:
            bool: True if the distribution is within the allowed difference, False otherwise.
        """ 

        # Convert valuation values to numeric
        historical_df['Valuation_Value'] = historical_df['Valuation_Value'].astype(float)
        df['Valuation_Value'] = df['Valuation_Value'].astype(float)

        # Assign valuation buckets
        historical_df['Valuation_Bucket'] = historical_df['Valuation_Value'].apply(assign_valuation_bucket)
        df['Valuation_Bucket'] = df['Valuation_Value'].apply(assign_valuation_bucket)

        proportions_dict = {}
        cols_to_check = ['Stage', 'ParentCategories_PrimaryCategoryName', 'State', 'Valuation_Bucket']

        # Generate value counts for the current and historical data
        logging.info("Generating column proportions for historical and current data...")
        proportions_dict = generate_column_proportions(historical_df, cols_to_check, 'historical')
        proportions_dict.update(generate_column_proportions(df, cols_to_check, 'current'))

        # Check for significant differences in distributions
        logging.info("Calcuating differences in distributions...")
        for col in cols_to_check:

            # Fetch the current and historical proportions for this column
            current_proportion = proportions_dict[f"{col}_current"]
            historical_proportion = proportions_dict[f"{col}_historical"]

            # Merge the current and historical proportions on the column name 
            # Used if the values of the column names in the current data does not match the historical data
            merged_proportions_df = historical_proportion.merge(current_proportion, 
                                                                on=col, suffixes=('_historical', '_current'))

            # Calculate the difference in proportions
            diff = abs(merged_proportions_df['Proportion_historical'] - merged_proportions_df['Proportion_current'])
            if diff.max() > max_diff: 
                logging.warning(f"Significant difference detected in {col} distribution.")
                return False 
            
        logging.info(f"No significant difference detected")
        return True
    
    def find_best_k_clusters(X, max_cluster, random_state): 

        max_cluster = min(max_cluster, len(X) - 1) # Cap the max cluster size to the number of samples - 1
        K = range(2, max_cluster)
        sil_scores = []
        
        for k in K: 
            kmeans = KMeans(n_clusters=k, random_state=random_state) # Apply k-means clustering
            kmeans.fit(X)
            score = silhouette_score(X, kmeans.labels_)
            sil_scores.append(score)

        best_k = K[np.argmax(sil_scores)] # Get the best k value using silhouette score

        logging.info(f"Best k value: {best_k} clusters with silhouette score: {max(sil_scores)}")

        return best_k
            
    with open(dataset.path, 'r') as f:
        df = pd.read_csv(f)

    logging.info("Preprocessing data...")

    # Reorder columns
    df = df[[
        id_col, 
        search_id_col, 
        search_name_col, 
        query_col, 
        territory_id_col, 
        territory_distance_col, 
        materials_valuation_col, 
        response_col
    ] + ranking_cols]

    # Drop rows with missing values in key columns
    df.dropna(subset = [id_col, search_id_col, search_name_col, query_col, response_col], inplace=True)
    df.reset_index(drop=True, inplace=True)
    logging.info(f"Length of df after dropping missing values: {len(df)}")

    df[id_col] = df[id_col].astype(str)

    preprocessed_df = df.copy()
    pool_df = df.copy()

    if clustering and column_types is not None: 

        logging.info("Applying clustering to data for sampling and deduplication...")

        # Clustering parameters
        max_clusters = clustering_inf.get("max_clusters", 10)
        sample_frac = clustering_inf.get("sample_frac", 0.8)

        cat_cols = column_types.get("cat_cols") 
        num_cols = column_types.get("num_cols")
        text_cols = column_types.get("text_cols") 
        
        encoded_df = encode_df_for_clustering(df=df, cat_cols=cat_cols, num_cols=num_cols, 
                                                text_cols=text_cols, sentence_transformer_name=sentence_transformer_name)
        logging.info("Length of encoded df: " + str(len(encoded_df)))

        # Fit best k-means clustering model
        logging.info("Performing k-means clustering...")
        best_k = find_best_k_clusters(encoded_df, max_clusters, random_state)
        model = KMeans(n_clusters=best_k, random_state=random_state)
        model.fit(encoded_df)

        # Add cluster labels to the original dataframe
        labels = model.labels_
        df['Cluster'] = labels

        # Sample data from each clusters
        logging.info("Sampling data from each cluster...")

        # Cap the sample size to the max_sample_size
        if len(df) > max_sample_size:
            sample_frac = max_sample_size / len(df)
            logging.info(f"Sample fraction set to {sample_frac} to limit data size to {max_sample_size}")
        else:
            logging.info(f"Data does not exceed max sample size of {max_sample_size}. Current sample fraction: {sample_frac}")

        sample_df = pd.DataFrame() 
        for cluster in df['Cluster'].unique():
            cluster_df = df[df['Cluster'] == cluster]
            logging.info(f"Length of cluster {cluster} df: {len(cluster_df)}")
            cluster_sample_size = int(len(cluster_df) * sample_frac)
            logging.info(f"Sampling {cluster_sample_size} rows from cluster {cluster}")
            sample_df = pd.concat([sample_df, cluster_df.sample(n=cluster_sample_size, random_state=random_state)])
            
        sample_df.reset_index(drop=True, inplace=True)
        preprocessed_df = sample_df.copy()
        pool_df = pool_df[~pool_df.index.isin(preprocessed_df.index)]


    # Perform SRS sampling if clustering is not enabled
    else: 
        if len(df) > max_sample_size:
            preprocessed_df = df.sample(n=max_sample_size, random_state=random_state)
            pool_df = pool_df[~pool_df.index.isin(preprocessed_df.index)]
            logging.info(f"Sample size limited to {max_sample_size}")
        else: 
            pool_df = pd.DataFrame()

    # Check distribution of data is within historical data
    logging.info("Checking distribution of data is within historical data...")
    is_within_historical_data = check_distribution_is_within_historical_data(historical_df=df,
                                                                             df=preprocessed_df,
                                                                             max_diff=max_diff)
    
    if not is_within_historical_data:
        logging.error("Distribution of data is not within historical data.")
        raise ValueError("Distribution of data is not within historical data. Ending pipeline run.")

    # Drop columns that are not needed for the tuning pipeline
    preprocessed_df = preprocessed_df[[
        id_col, 
        search_id_col, 
        search_name_col, 
        query_col, 
        territory_id_col, 
        territory_distance_col, 
        materials_valuation_col, 
        response_col
    ] + ranking_cols]   

    logging.info(f"Data preprocessing complete. df: {preprocessed_df.head()}")

    # Make temp dir 
    os.makedirs('tmp', exist_ok=True)

    # Save preprocessed data to CSV
    output_csv = f"{output_filename}/{uuid}/data.csv"
    tmp = 'tmp/data.csv'
    preprocessed_df.to_csv(tmp, index=False)
    try:
        logging.info(f"Attempting to upload file to bucket: {bucket} with filename: {output_csv}")
        dataset_gcs_uri = upload_file_to_gcs(tmp, bucket, output_csv)
        logging.info(f"File {output_csv} successfully uploaded to GCS bucket {dataset_gcs_uri}")
    except Exception as e:
        logging.error(f"Failed to upload file {output_csv} to GCS. Error: {str(e)}")
        raise

    if not pool_df.empty: 
        pool_csv = f"{output_filename}/{uuid}/pool.csv"
        tmp = 'tmp/pool.csv'
        pool_df.to_csv(tmp, index=False)
        try:
            logging.info(f"Attempting to upload file to bucket: {bucket} with filename: {pool_csv}")
            pool_gcs_uri = upload_file_to_gcs(tmp, bucket, pool_csv)
            logging.info(f"File {pool_csv} successfully uploaded to GCS bucket {pool_gcs_uri}")
        except Exception as e:
            logging.error(f"Failed to upload file {pool_csv} to GCS. Error: {str(e)}")
            raise
    else: 
        pool_gcs_uri = ""

    outputs = NamedTuple('outputs', [('dataset_gcs_uri', str), ('pool_gcs_uri', str)])
    return outputs(dataset_gcs_uri, pool_gcs_uri)

if __name__ == "__main__":
    Compiler().compile(preprocess_data, package_path="preprocess_data.yaml")