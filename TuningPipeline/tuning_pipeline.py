import json 
from typing import List, Optional 
from kfp import dsl, components
from kfp.compiler import Compiler 
import google.cloud.aiplatform as aip 
from typing import NamedTuple, List 
from uuid import uuid4
import nltk

import argparse 
parser = argparse.ArgumentParser("tuning_pipeline")
parser.add_argument('-c', '--config_path', type=str, required=True)
parser.add_argument('-s', '--service_account', type=str, required=True)
parser.add_argument('-t', '--is_testing', type=bool, required=False, default=False)
pargs = vars(parser.parse_args())

config_path = pargs['config_path']
SERVICE_ACCOUNT = pargs['service_account']
is_testing = pargs['is_testing']

ingest_data = components.load_component_from_file('components/ingest_data.yaml')
preprocess_data = components.load_component_from_file('components/preprocess_data.yaml')
split_data = components.load_component_from_file('components/split_data.yaml')
format_tuning_data = components.load_component_from_file('components/format_tuning_data.yaml')
tune_model = components.load_component_from_file('components/tune_model.yaml')
evaluate_model = components.load_component_from_file('components/evaluate_model.yaml')
save_ouputs = components.load_component_from_file('components/save_outputs.yaml')

@dsl.pipeline(name='tuning_pipeline',)
def tuning_pipeline(
    # Project parameters
    project_id: str, 
    location: str,
    bucket: str, 
    uuid: str,

    # Dynamics manager parameter
    dm_instance_url: str,

    # Data column parameters
    id_col: str, 
    search_id_col: str, 
    search_name_col: str, 
    query_col: str, 
    territory_id_col: str,
    territory_distance_col: str,
    materials_valuation_col: str,
    response_col: str,

    # Data source parameters
    bq_dataset: str,
    cc_bq_table: str,
    dodge_bq_table: str,
    ranking_cols_bq_table: str,
    boolean_filters_bq_table: str,
    territories_bq_table: str, 
    search_product_map_bq_table: str,
    consolidated_projects_bq_table: str, 
    coalesced_projects_bq_table: str,

    # Sales data source parameters 
    sales_project_id: str, 
    sales_bq_dataset: str, 
    sales_table: str,  
    sales_customer_table: str, 

    # Representative sampling parameters 
    max_diff: float,
    
    # Output data parameters
    data_output_filename: str,
    formatted_data_output_filename: str,
    model_output_bq_dataset: str,

    # LLM prompt for relevance
    prompt: str, 
    
    # Model parameters
    model_display_name: str, 
    base_model_name: str = "gemini-2.0-flash-001",

    # OPTIONAL PARAMETERS
    # Sampling parameters
    max_sample_size: int = 1000,
    clustering: bool = False, 
    clustering_inf: Optional[dict] = None,
    sentence_transformer_name: str = "all-MiniLM-L6-v2",

    # Train/test parameters
    seed: int = 42,
    training_split: float = 0.8,
    validation_split: float = 0.2,
    split_by_similarity: bool = False,
    similarity_threshold: float = 0.8,
    column_types: Optional[dict] = None,
    max_test_size_reduction: float = 0,

    # Historical data parameters
    historical_days: int = 60,

    # Tuning parameters
    epochs: int = 10,
    adapter_size: int = 4, 

    # Evaluation parameters 
    labels: List[str] = ['Very High', 'High', 'Moderate', 'Low', 'Not Relevant'],

    is_testing: bool = False,
): 
    
    # Ingest data 
    ingest_op = ingest_data(
        project_id=project_id,
        location = location,
        dm_instance_url=dm_instance_url,
        bq_dataset=bq_dataset, 
        id_col=id_col,
        search_id_col=search_id_col,
        search_name_col=search_name_col,
        query_col=query_col,
        territory_id_col=territory_id_col,
        territory_distance_col=territory_distance_col,
        materials_valuation_col=materials_valuation_col,
        response_col=response_col, 
        boolean_filters_bq_table=boolean_filters_bq_table, 
        ranking_cols_bq_table=ranking_cols_bq_table,
        coalesced_projects_bq_table=coalesced_projects_bq_table, 
        is_testing=is_testing
    )

    ranking_columns = ingest_op.outputs['ranking_columns']
    
    # Preprocess data
    preprocess_op = preprocess_data(
        project_id=project_id,
        bucket=bucket,
        uuid=uuid,
        id_col=id_col,
        search_id_col=search_id_col,
        search_name_col=search_name_col,
        query_col=query_col,
        territory_id_col=territory_id_col,
        territory_distance_col=territory_distance_col,
        materials_valuation_col=materials_valuation_col,
        response_col=response_col,
        ranking_cols=ranking_columns,
        dataset = ingest_op.outputs['dataset'],
        max_diff=max_diff,
        output_filename=data_output_filename,
        max_sample_size=max_sample_size,
        clustering=clustering,
        clustering_inf=clustering_inf, 
        column_types=column_types,
        sentence_transformer_name=sentence_transformer_name,
        random_state=seed
    )

    split_data_op = split_data(
        project_id=project_id,
        bucket=bucket, 
        dataset_gcs_uri=preprocess_op.outputs['dataset_gcs_uri'],
        pool_gcs_uri=preprocess_op.outputs['pool_gcs_uri'],
        id_col=id_col,
        search_id_col=search_id_col,
        territory_id_col=territory_id_col,
        response_col=response_col, 
        training_split=training_split,
        validation_split=validation_split,
        split_by_similarity=split_by_similarity,
        similarity_threshold=similarity_threshold,
        max_test_size_reduction=max_test_size_reduction,
        column_types=column_types,
        sentence_transformer_name=sentence_transformer_name,
        random_state=seed,
    )
    
    format_tuning_data_op = format_tuning_data(
        project_id=project_id,
        bucket=bucket,
        uuid=uuid, 
        prompt=prompt,
        id_col=id_col,
        search_id_col=search_id_col,
        search_name_col=search_name_col,
        query_col=query_col,
        territory_id_col=territory_id_col,
        materials_valuation_col=materials_valuation_col,
        bq_dataset=bq_dataset,
        territory_table=territories_bq_table,
        search_product_map_table=search_product_map_bq_table, 
        cc_feed_table=cc_bq_table,
        dodge_feed_table=dodge_bq_table,
        consolidated_projects_bq_table=consolidated_projects_bq_table,
        sales_project_id=sales_project_id,
        sales_dataset=sales_bq_dataset,
        sales_table=sales_table,
        customer_table=sales_customer_table,
        X_train=split_data_op.outputs['X_train_output'],
        y_train=split_data_op.outputs['y_train_output'],
        X_valid=split_data_op.outputs['X_valid_output'],
        y_valid=split_data_op.outputs['y_valid_output'], 
        X_test=split_data_op.outputs['X_test_output'],
        y_test=split_data_op.outputs['y_test_output'],
        output_filename=formatted_data_output_filename,
        historical_days=historical_days,
    )

    # Tune model
    tune_model_op = tune_model(
        uuid=uuid,
        project_id=project_id,
        location=location,
        training_dataset_uri=format_tuning_data_op.outputs['formatted_training_dataset_gcs_uri'],
        validation_dataset_uri=format_tuning_data_op.outputs['formatted_validation_dataset_gcs_uri'],
        model_display_name=model_display_name,
        base_model_name=base_model_name,
        epochs=epochs,
        adapter_size=adapter_size,
        is_testing=is_testing
    )

    # Evaluate model
    evaluate_model_op = evaluate_model(
        project_id=project_id,
        location=location,
        bucket=bucket,
        id_col=id_col,
        response_col=response_col,
        base_model=tune_model_op.outputs['base_model_endpoint'],
        tuned_model_endpoint=tune_model_op.outputs['tuned_model_endpoint'],
        X_test_formatted_gcs_uri=format_tuning_data_op.outputs['formatted_testing_dataset_gcs_uri'],    
        y_test=split_data_op.outputs['y_test_output'],
        labels=labels
    )

    # Save outputs
    _ = save_ouputs(
        project_id=project_id,
        uuid=uuid,
        bq_dataset=bq_dataset,
        model_output_bq_dataset=model_output_bq_dataset,
        preprocessed_data_uri=preprocess_op.outputs['dataset_gcs_uri'], 
        base_model_name=evaluate_model_op.outputs["base_model"],
        tuned_model_name=evaluate_model_op.outputs["tuned_model"],
        performance_metrics=evaluate_model_op.outputs['performance_metrics'],
    )

Compiler().compile(pipeline_func=tuning_pipeline, 
                package_path='tuning_pipeline.yaml')

with open(config_path, 'r') as f:
    args = json.load(f)

PROJECT_ID = args['project_id']
LOCATION = args['location']
BUCKET = args['bucket']

uuid = str(uuid4())  # Generate a unique ID for the pipeline run
args['uuid'] = uuid
args['is_testing'] = is_testing
model = args['base_model_name'].replace('.', '-')
print(model)


pipeline_labels = { 
    'pipeline_name': 'tuning_pipeline',
    'adapter_size': str(args.get('adapter_size', 4)),
    'epochs': str(args.get('epochs', 20)),
    'base_model': model,
    'uuid': uuid, 
}

aip.init(project=PROJECT_ID, location=LOCATION)

# Prepare the pipeline job
job = aip.PipelineJob(
    display_name=f"tuning_pipeline",
    template_path='tuning_pipeline.yaml',
    pipeline_root=f'gs://{BUCKET}/pipeline_root/',
    parameter_values=args,
    labels=pipeline_labels,
    enable_caching=True,
    # enable_caching=False
)

job.submit(service_account=SERVICE_ACCOUNT)