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
def save_outputs(project_id: str, 
                 uuid: str, 
                 bq_dataset: str, 
                 model_output_bq_dataset: str, 
                 preprocessed_data_uri: str,
                 base_model_name: str, 
                 tuned_model_name: str,
                 performance_metrics: dict,
                 ): 
    
    import pandas_gbq
    from datetime import datetime 
    import pandas as pd 
    import json

    base_performance = json.dumps(performance_metrics['base_model'])
    tuned_performance = json.dumps(performance_metrics['tuned_model'])

    current_time = pd.to_datetime(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    # Format the output
    output_df = pd.DataFrame({
        'base_model': [base_model_name],
        'tuned_model': [tuned_model_name],
        'date': [current_time],
        'pipeline_run_uuid': [uuid],
        'base_model_performance': [base_performance],
        'tuned_model_performance': [tuned_performance],
        'data_uri': [preprocessed_data_uri], 
        'llm_prompt_type': ['assign_relevance']
    })

    table_schema = [{'name': 'base_model', 'type': 'STRING'},
                    {'name': 'tuned_model', 'type': 'STRING'},
                    {'name': 'date', 'type': 'DATETIME'},
                    {'name': 'pipeline_run_uuid', 'type': 'STRING'},
                    {'name': 'base_model_performance', 'type': 'STRING'},
                    {'name': 'tuned_model_performance', 'type': 'STRING'},
                    {'name': 'data_uri', 'type': 'STRING'},
                    {'name': 'llm_prompt_type', 'type': 'STRING'}]

    # Write to BigQuery
    pandas_gbq.to_gbq(output_df,
                        destination_table=f'{project_id}.{bq_dataset}.{model_output_bq_dataset}',
                        project_id=project_id,
                        table_schema=table_schema,
                        if_exists='append')

if __name__ == "__main__":
    Compiler().compile(save_outputs, package_path="save_outputs.yaml")