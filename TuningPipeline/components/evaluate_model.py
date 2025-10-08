import kfp
from kfp.dsl import component, Output, Dataset, Input
from kfp.compiler import Compiler
from typing import List, NamedTuple
import argparse

def get_base_image():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base_image', type=str)
    args, _ = parser.parse_known_args()
    return args.base_image

@component(base_image=get_base_image(), install_kfp_package=False)
def evaluate_model(project_id: str, 
                location: str,
                bucket: str,
                id_col: str,
                response_col: str,
                base_model: str,
                tuned_model_endpoint: str, 
                X_test_formatted_gcs_uri: str,
                y_test: Input[Dataset], 
                labels: List[str]) -> NamedTuple('outputs', [('performance_metrics', dict), ('base_model', str), ('tuned_model', str)]):
    
    from tqdm import tqdm
    import json 
    import logging
    import pandas as pd 
    from google import genai
    from sklearn.preprocessing import LabelEncoder 
    from sklearn.metrics import f1_score, recall_score, precision_score
    from utils import download_file_from_gcs
    from google.genai.types import GenerateContentConfig
    import os
    import numpy as np

    def strip_json(output: str, response_col: str): 
        """
        This function strips the JSON output and returns the response classification.
        """
        try: 
            output_stripped = output.replace("```json", "").replace("```", "").replace("[", "").replace("]", "").strip()
            output_json = json.loads(output_stripped)
            response = str(output_json[response_col])
            return response

        except Exception as e:
            logging.info(f"Error stripping JSON: %s", e)
            logging.info(f"Output: {output}")
            return None 

    # Suppress HTTPX and Google GenAI logging
    logging.getLogger('google_genai').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING) 

    # Download the X_test_formatted file from GCS
    logging.info(f"Downloading X_test_formatted from GCS: {X_test_formatted_gcs_uri}")
    os.makedirs("tmp", exist_ok=True)
    local_file_path = "tmp/formatted_testing_data.jsonl"
    blob_name = X_test_formatted_gcs_uri.replace(f"gs://{bucket}/", "")
    download_file_from_gcs(bucket_name=bucket,
                            blob_name=blob_name,
                            local_file_path=local_file_path)

    # Read the X_test_formatted file
    logging.info(f"Reading X_test_formatted from local file: {local_file_path}")
    X_test_formatted = []
    with open(local_file_path, 'r') as f:
        for line in f:
            X_test_formatted.append(json.loads(line))

    # Read the y_test file 
    with open(y_test.path, 'r') as f:
        y_test_df = pd.read_csv(f)

    # Create the generation config
    generation_config = { 
        "temperature": 0,
        "candidate_count": 1,
        "seed": 42,
        "max_output_tokens": 8192,
        "response_mime_type": "application/json", 
        "response_schema": {
            "type": "OBJECT",
            "properties": {
                id_col: {"type": "STRING"},  # Use the provided id_col for the id column
                response_col: {"type": "STRING", 
                                "enum": labels},  # Use the provided labels for the response column
            },
            "required": [id_col, response_col]
        }
    }

    # Create the generation config without the response schema for tuned models
    generation_config_no_response_schema = generation_config.copy()
    del generation_config_no_response_schema["response_schema"]
    del generation_config_no_response_schema["response_mime_type"]

    # Create genai client
    client = genai.Client(vertexai=True, project=project_id, location=location)

    # Create predictions DataFrame
    predictions_df = y_test_df.copy() 
    predictions_df[f"{response_col}_tuned"] = None  # Predictions for tuned model 
    predictions_df[f"{response_col}_base"] = None  # Predictions for base model 

    # Generate predictions 
    logging.info("Generating predictions for test data...")
    
    for idx, X_test in tqdm(enumerate(X_test_formatted), total=len(X_test_formatted)):
        
        # Generate content using the tuned and base
        base_response = client.models.generate_content(model=base_model, contents=X_test["contents"][0], 
        config=GenerateContentConfig(**generation_config))

        tuned_response = client.models.generate_content(model=tuned_model_endpoint, contents=X_test["contents"][0], 
        config=GenerateContentConfig(**generation_config_no_response_schema))
        
        try: 
            # Parse predictions to DataFrame with project id and search
            tuned_prediction = strip_json(output=tuned_response.text,
                                          response_col=response_col
                                        )
            
            base_prediction = strip_json(output=base_response.text,
                                          response_col=response_col
                                        )

            df_index = predictions_df.index[idx] # Get the index of the row in the predictions DataFrame
                
            # Add the predictions to the predictions DataFrame
            if tuned_prediction is not None:
                predictions_df.loc[df_index, f"{response_col}_tuned"] = tuned_prediction
            if base_prediction is not None:
                predictions_df.loc[df_index, f"{response_col}_base"] = base_prediction

        except Exception as e: 
            logging.error(f"Error parsing predictions: {e}")
            continue

    # Drop rows with empty values
    predictions_df = predictions_df.dropna()
    logging.info(f"Predictions data: {predictions_df.head()}")

    logging.info(predictions_df[response_col].value_counts())
    logging.info(predictions_df[f"{response_col}_tuned"].value_counts())
    logging.info(predictions_df[f"{response_col}_base"].value_counts())

    # Encode the relevance columns
    logging.info("Encoding relevance columns...")
    relevance_columns = predictions_df.filter(regex=response_col).columns

    # Initialize the encoder with the label set
    encoder = LabelEncoder()
    encoder.fit([label.lower() for label in labels])
    
    for col in relevance_columns:
        predictions_df.loc[:, col] = predictions_df[col].astype(str).str.lower()
        predictions_df.loc[:, f"{col}_label"] = encoder.transform(predictions_df[col])

    logging.info(f"Predictions DataFrame created with encoded columns: {predictions_df.columns.tolist()}")
    logging.info("Predictions df: %s", predictions_df.head())
    
    # Calculate performance metrics
    logging.info("Calculating performance metrics...")
    performance_metrics = {"base_model": {}, "tuned_model": {}} 
    metrics = {"f1": f1_score,
              "recall": recall_score,
              "precision": precision_score}
    
    for model_type in ["base_model", "tuned_model"]:
        model_col_label = model_type.split("_")[0]
        llm_predictions_col = f"{response_col}_{model_col_label}_label"

        for metric_name, metric_func in metrics.items():
            try:
                performance_metrics[model_type][metric_name] = metric_func(
                    predictions_df[f"{response_col}_label"], 
                    predictions_df[llm_predictions_col],
                    average='weighted'
                )
            except Exception as e:
                logging.error(f"Error calculating {metric_name} for {model_type}: {e}")
                performance_metrics[model_type][metric_name] = None


    for model_type in ["base_model", "tuned_model"]: 
        for metric_name, value in performance_metrics[model_type].items(): 
            if value is None or value == np.nan: 
                performance_metrics[model_type][metric_name] = ""

    logging.info(f"Performance metrics: {performance_metrics}")

    outputs = NamedTuple('outputs', [('performance_metrics', dict), ('base_model', str), ('tuned_model', str)])

    return outputs(performance_metrics=performance_metrics, base_model=base_model, tuned_model=tuned_model_endpoint)


if __name__ == "__main__":
    Compiler().compile(evaluate_model, package_path="evaluate_model.yaml")