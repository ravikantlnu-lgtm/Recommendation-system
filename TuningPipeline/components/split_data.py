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
def split_data(project_id: str,
                bucket: str,
                dataset_gcs_uri: str,
                pool_gcs_uri: str,

                # Data parameters
                id_col: str,
                search_id_col: str, 
                territory_id_col: str,
                response_col: str,

                # Output parameters 
                X_train_output: Output[Dataset],
                y_train_output: Output[Dataset],
                X_valid_output: Output[Dataset],
                y_valid_output: Output[Dataset],
                X_test_output: Output[Dataset],
                y_test_output: Output[Dataset],

                # Split parameters 
                training_split: float = .8,
                validation_split: float = .1,
                split_by_similarity: bool = True,
                similarity_threshold: float = 0.8,
                max_test_size_reduction: float = 0,
                column_types: dict = None,
                sentence_transformer_name: str = "all-MiniLM-L6-v2",
                random_state: int = 42,
                ): 

    import logging
    import pandas as pd 
    import numpy as np
    from google.cloud import bigquery
    from sklearn.model_selection import train_test_split
    from utils import download_file_from_gcs, encode_df_for_clustering
    from sklearn.metrics.pairwise import cosine_similarity 
    import math

    def calculate_exceeds_threshold_matrix(df: pd.DataFrame, similarity_threshold: float = 0.8, chunk_size: int = 1000): 

        """ 
        This function calculates the cosine similarity between all pairs of rows in an encoded dataframe and returns a matrix indicating whether the similarity exceeds a given threshold.
        Args:
            df: DataFrame with encoded (numerical, categorical, text) columns
            similarity_threshold: Threshold for cosine similarity
            chunk_size: Size of chunks to process at a time
        Returns:
            results_matrix: Matrix indicating whether two projects exceed the similarity threshold. matrix[i,j] = True if project i and j exceed the threshold.
        """

        n_samples = df.shape[0]
        num_chunks = math.ceil(n_samples / chunk_size)

        results_matrix = np.zeros((n_samples, n_samples), dtype=bool)

        for i in range(num_chunks):

            # Fetch chunk_i
            i_start = i * chunk_size 
            i_end = min((i + 1) * chunk_size, n_samples)
            chunk_i = encoded_df[i_start:i_end]

            # Compare chunk_i against all chunk_j 
            for j in range(i, num_chunks): 
                j_start = j * chunk_size
                j_end = min((j + 1) * chunk_size, n_samples)
                chunk_j = encoded_df[j_start:j_end]

                # Compute similarity between chunk_i and chunk_j 
                similarity_block = cosine_similarity(chunk_i, chunk_j)

                # Fetch indices of similarity above threshold
                rows, cols = np.where(similarity_block > similarity_threshold)

                for row_in_block, col_in_block in zip(rows, cols): 

                    # Fetch original indices
                    row_idx = i_start + row_in_block
                    column_idx = j_start + col_in_block

                    # Save similarity to results matrix without duplicates
                    if i == j: 
                        if row_idx < column_idx: 
                            results_matrix[row_idx, column_idx] = similarity_block[row_in_block, col_in_block] > similarity_threshold
                    else: 
                        results_matrix[row_idx, column_idx] = similarity_block[row_in_block, col_in_block] > similarity_threshold

            logging.info(f"Chunk {i + 1}/{num_chunks} processed.")
        
        logging.info("Calculating exceeds threshold matrix completed.")
        logging.info("Data type of results matrix: " + str(results_matrix.dtype))

        return results_matrix

    def split_data_by_similarity(df: pd.DataFrame,
                                 pool_df: pd.DataFrame,
                                 exceeds_threshold_matrix: np.ndarray,
                                 train_size: float = 0.8, 
                                 random_state: int = 42, 
                                 max_test_size_reduction: float = 0):
        
        """
        This function splits a dataframe into training and testing sets based on cosine similarity.
        If a test project is too similar to a training project, it is removed from the test set.
        Args:
            df: DataFrame with original project data.
            pool_df: DataFrame with additional rows to be used as a pool.
            exceeds_threshold_matrix: Matrix indicating whether two projects exceed the similarity threshold. matrix[i,j] = True if project i and j exceed the threshold.
            train_size: Proportion of data to use for training
            random_state: Random seed

        Returns:
            train_df: DataFrame with training data
            test_df: DataFrame with testing data
        """

        logging.info(f"matrix: {exceeds_threshold_matrix}")
        logging.info("Size of exceeds threshold matrix: " + str(exceeds_threshold_matrix.shape))
        logging.info("Data type of exceeds threshold matrix: " + str(exceeds_threshold_matrix.dtype))

        indices = list(range(len(df)))
        df_and_pool = pd.concat([df, pool_df], axis=0) if not pool_df.empty else df
        
        # Split data into training and testing sets
        train_indices, test_indices = train_test_split(
            indices, train_size=train_size, random_state=random_state
        )

        # Calculate the minimum number of test data points needed
        min_num_tests = int(len(test_indices) * (1 - max_test_size_reduction)) 
        logging.info(f"Minimum size of test data needed: {min_num_tests}")

        # Check test data point similarity against training data points
        for test_idx in test_indices[:]: 
            for train_idx in train_indices: 
                smaller_idx = min(train_idx, test_idx)
                bigger_idx = max(train_idx, test_idx)
                if exceeds_threshold_matrix[smaller_idx, bigger_idx]:  # train, test indices exceed similarity threshold
                    test_indices.remove(test_idx)  # Remove test index from testing indices
                    break 

        logging.info(f"Number tests after removing similar rows {len(test_indices)}")
        
        # Continuously add more test data points from the pool
        pool_indices = list(range(len(df), len(exceeds_threshold_matrix)))  # Indices of the pool
        logging.info(f"Size of pool: {len(pool_indices)}")

        while len(test_indices) < min_num_tests and len(pool_indices) > 0:  # Ends when either we reach min_num_tests or we have no more rows in the pool

            logging.info(f"Adding more rows from the pool to test data...")
            additional_indices_to_add = pool_indices[:min_num_tests - len(test_indices)] # Fetch indices to add from the pool
            pool_indices = pool_indices[min_num_tests - len(test_indices):]  # Remove added indices from the pool
            test_indices.extend(additional_indices_to_add)  # Add to test indices
            
            # Check the new pool indicies against training data points
            for test_idx in additional_indices_to_add: 
                for train_idx in train_indices:
                    smaller_idx = min(train_idx, test_idx)
                    bigger_idx = max(train_idx, test_idx)
                    if exceeds_threshold_matrix[smaller_idx, bigger_idx]: 
                        test_indices.remove(test_idx)
                        break 
            logging.info(f"Number tests after adding from pool and removing similar rows: {len(test_indices)}")
            logging.info("Size of remaining pool: " + str(len(pool_indices)))

        # Check if we still do not have enough test data points 
        if len(test_indices) < min_num_tests:
            raise ValueError("Not enough test data points. Ending pipeline run.") # Raise error
             
        train_df = df_and_pool.iloc[train_indices]
        test_df = df_and_pool.iloc[test_indices]

        return train_df, test_df
    

    client = bigquery.Client()

    # Download dataset from GCS
    logging.info(f"Downloading dataset from GCS: {dataset_gcs_uri}")
    filename = 'preprocessed_data.csv'
    download_file_from_gcs(bucket_name=bucket, 
                           blob_name=dataset_gcs_uri.replace(f'gs://{bucket}/', ''),
                           local_file_path=filename)
    
    df = pd.read_csv(filename)
    
    # Download pool dataset from GCS if provided
    if pool_gcs_uri is not None and pool_gcs_uri != '':
        logging.info(f"Downloading pool dataset from GCS: {pool_gcs_uri}")
        pool_filename = 'pool_data.csv'
        download_file_from_gcs(bucket_name=bucket, 
                               blob_name=pool_gcs_uri.replace(f'gs://{bucket}/', ''),
                               local_file_path=pool_filename)
        
        pool_df = pd.read_csv(pool_filename)
    else: 
        pool_df = pd.DataFrame()
        
    logging.info(f"Size of dataset: {df.shape}")
    logging.info(f"Size of pool dataset: {pool_df.shape}")

    # Split data into training and testing sets
    logging.info("Splitting data into training and testing sets...")

    if split_by_similarity and column_types is not None:

        logging.info("Splitting data using cosine similarity...")
        cat_cols = column_types.get("cat_cols") 
        num_cols = column_types.get("num_cols")
        text_cols = column_types.get("text_cols") 

        # Concatenate the pool_df with the original df for encoding and similarity calculation
        df_and_pool = pd.concat([df, pool_df], axis=0) if not pool_df.empty else df
        df_and_pool.reset_index(drop=True, inplace=True)
    
        # Encode categorical, numerical, and text cols
        encoded_df = encode_df_for_clustering(df=df_and_pool, cat_cols=cat_cols, num_cols=num_cols, text_cols=text_cols, 
                                                sentence_transformer_name=sentence_transformer_name)

        logging.info("Calculating similarities between rows using encodings dataframe...")
        exceeds_threshold_matrix = calculate_exceeds_threshold_matrix(df=encoded_df, 
                                                                        similarity_threshold=similarity_threshold)

        # Split data by similarity
        logging.info("Splitting data into train, test, and validation by similarity...")
        train_df, test_df = split_data_by_similarity(df=df, 
                                                     pool_df=pool_df,
                                                    exceeds_threshold_matrix=exceeds_threshold_matrix,
                                                    train_size=training_split,
                                                    random_state=random_state, 
                                                    max_test_size_reduction=max_test_size_reduction)
        
        # Split into training/validation
        valid_df = train_df.sample(frac=validation_split, random_state=random_state)
        train_df = train_df.drop(valid_df.index)
        
        logging.info("Shape of train_df: " + str(train_df.shape))
        logging.info("Shape of test_df: " + str(test_df.shape))
        logging.info("Shape of valid_df: " + str(valid_df.shape))

        # Construct X, y training, validation, and test datasets
        logging.info("Constructing X, y training, validation, and test datasets...")
        X_train = train_df.drop(columns = [response_col])
        X_valid = valid_df.drop(columns = [response_col])
        X_test = test_df.drop(columns = [response_col])

        y_train = pd.concat([pd.DataFrame(X_train[id_col]), train_df[response_col]], axis=1)
        y_valid = pd.concat([pd.DataFrame(X_valid[id_col]), valid_df[response_col]], axis=1)
        y_test = pd.concat([pd.DataFrame(X_test[id_col]), test_df[[search_id_col, territory_id_col, response_col]]], axis=1)

    else:                 
        
        # Split data into training, validation, and testing sets with traditional method
        logging.info("Splitting data into trainning, testing, and validation...")
        X = df.drop(columns = [response_col])
        y = df[response_col]
        X_train, X_test, y_train, y_test = train_test_split(X, y, train_size=training_split, random_state=random_state)
        X_train, X_valid, y_train, y_valid = train_test_split(X_train, y_train, train_size=1-validation_split, random_state=random_state)

        # Add ID column back 
        y_train = pd.concat([pd.DataFrame(X_train[id_col]), y_train], axis=1)
        y_valid = pd.concat([pd.DataFrame(X_valid[id_col]), y_valid], axis=1)
        y_test = pd.concat([X_test[[id_col, territory_id_col, search_id_col]], y_test], axis=1)
    
    logging.info(f"Saving data to output dataset paths...")
    # Save test data to output dataset paths
    X_train.to_csv(X_train_output.path, index=False)
    y_train.to_csv(y_train_output.path, index=False)
    X_valid.to_csv(X_valid_output.path, index=False)
    y_valid.to_csv(y_valid_output.path, index=False)
    X_test.to_csv(X_test_output.path, index=False)
    y_test.to_csv(y_test_output.path, index=False)

if __name__ == "__main__":
    Compiler().compile(split_data, package_path="split_data.yaml")