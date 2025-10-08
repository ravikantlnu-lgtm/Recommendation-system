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
def tune_model(uuid: str,
               project_id: str,
               location: str,
               training_dataset_uri: str,
               validation_dataset_uri: str, 
               model_display_name: str, 
               base_model_name: str = "gemini-2.0-flash-001",
               epochs: int = 10,
               adapter_size: int = 4, 
               is_testing: bool = False,
               ) -> NamedTuple('outputs', [('tuned_model_endpoint', str), 
                                           ('base_model_endpoint', str)]): 
    
    from vertexai.tuning import sft 
    import time
    import logging 
    from google import genai 
    from google.genai.types import TuningDataset, CreateTuningJobConfig, TuningValidationDataset

    # Only run this block for Vertex AI API
    client = genai.Client(
        vertexai=True, project=project_id, location=location
    )
    
    display_name = f"{model_display_name}_{uuid}_a_{adapter_size}_e_{epochs}"

    # Check if we're in testing mode
    if is_testing:
        if base_model_name == "gemini-2.5-flash":
            return "projects/195063057478/locations/us-central1/endpoints/6903135320921866240", base_model_name
        else: 
            return "projects/195063057478/locations/us-central1/endpoints/52254290110054400", base_model_name
    # --- end return tuned model for testing --- 

    training_dataset = TuningDataset(
        gcs_uri=training_dataset_uri 
    )   

    validation_dataset = TuningValidationDataset(
        gcs_uri=validation_dataset_uri
    )

    tuning_job = client.tunings.tune(
        base_model=base_model_name,
        training_dataset=training_dataset,
        config=CreateTuningJobConfig(
            tuned_model_display_name=display_name,
            validation_dataset=validation_dataset,
            epoch_count=epochs,
        )
    )

    running_states = set(
        [
            'JOB_STATE_RUNNING',
            'JOB_STATE_PENDING',
        ]
    )

    while tuning_job.state in running_states: 
        logging.info(tuning_job.state)
        tuning_job = client.tunings.get(name=tuning_job.name)
        time.sleep(180)

    tuned_model_endpoint = tuning_job.tuned_model.endpoint
    logging.info(f"Tuning job completed.")
    logging.info(f"Model endpoint: {tuned_model_endpoint}")

    outputs = NamedTuple('outputs', [('tuned_model_endpoint', str), 
                                           ('base_model_endpoint', str)])
    
    return outputs(tuned_model_endpoint=tuned_model_endpoint, 
                   base_model_endpoint=base_model_name)
    
if __name__ == "__main__":
    Compiler().compile(tune_model, package_path="tune_model.yaml")