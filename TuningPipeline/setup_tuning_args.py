import json 
from dotenv import load_dotenv
import os 
from relevance_prompt import RELEVANCE_PROMPT
def setup_args(): 

    env = os.getenv('ENV', default='dev') 
    if env == 'dev':
        env_file = '.env.DEV'
    elif env == 'prod':
        env_file = '.env.PROD'
    load_dotenv(env_file)

    # PROJECT PARAMETERS
    PROJECT_ID = os.getenv('PROJECT_ID')
    LOCATION = os.getenv('LOCATION')
    BUCKET = os.getenv('BUCKET')

    # URM FOR CRM
    DM_INSTANCE_URL = os.getenv('DM_INSTANCE_URL')

    # DATA COLUMN PARAMETERS
    ID_COL = os.getenv('ID_COL')
    SEARCH_ID_COL = os.getenv('SEARCH_ID_COL')
    SEARCH_NAME_COL = os.getenv('SEARCH_NAME_COL')
    QUERY_COL = os.getenv('QUERY_COL')
    TERRITORY_ID_COL = os.getenv('TERRITORY_ID_COL')
    TERRITORY_DISTANCE_COL = os.getenv('TERRITORY_DISTANCE_COL')
    MATERIALS_VALUATION_COL= os.getenv('MATERIALS_VALUATION_COL')
    RESPONSE_COL = os.getenv('RESPONSE_COL')

    # DATA SOURCE PARAMETERS
    BQ_DATASET = os.getenv('BQ_DATASET')
    CC_BQ_TABLE = os.getenv('CC_BQ_TABLE')
    DODGE_BQ_TABLE = os.getenv('DODGE_BQ_TABLE')
    RANKING_COLS_BQ_TABLE = os.getenv('RANKING_COLS_BQ_TABLE')
    BOOLEAN_FILTERS_BQ_TABLE = os.getenv('BOOLEAN_FILTERS_BQ_TABLE')
    TERRITORIES_BQ_TABLE = os.getenv('TERRITORIES_BQ_TABLE')
    SEARCH_PRODUCT_MAP_BQ_TABLE = os.getenv('SEARCH_PRODUCT_MAP_BQ_TABLE')
    CONSOLIDATED_PROJECTS_BQ_TABLE = os.getenv('CONSOLIDATED_PROJECTS_BQ_TABLE')
    COALESCED_PROJECTS_BQ_TABLE = os.getenv('COALESCED_PROJECTS_BQ_TABLE')

    # HISTORICAL SALES DATA PARAMETERES
    SALES_PROJECT_ID=os.getenv('SALES_PROJECT_ID')
    SALES_BQ_DATASET=os.getenv('SALES_BQ_DATASET') 
    SALES_TABLE=os.getenv('SALES_TABLE')
    SALES_CUSTOMER_TABLE=os.getenv('SALES_CUSTOMER_TABLE')
    HISTORICAL_DAYS = 60
        
    # SAMPLING PARAMETERS
    MAX_SAMPLE_SIZE = 1000     # Maximum sample size for the data
    CLUSTERING = False # Set to True to enable clustering for sampling/deduplication
    MAX_CLUSTERS = 10 
    SAMPLE_FRAC = .8
    CLUSTERING_INF = {
    "max_clusters": MAX_CLUSTERS, # Maximum number of clusters to create and test  
    "sample_frac": SAMPLE_FRAC, # Fraction of data to sample for clustering
}

    # SENTENCE TRANSFORMER NAME
    SENTENCE_TRANSFORMER_NAME = "all-MiniLM-L6-v2" # Sentence transformer model name for encoding text data

    # REPRESENTATIVE SAMPLING PARAMETERS
    MAX_DIFF = 0.5  # Maximum proportion difference allowed between historical/current data; used to check if the data is representative

    # TRAIN/TEST SPLIT PARAMETERS
    SEED = 42
    TRAINING_SPLIT = 0.8
    VALIDATION_SPLIT = 0.1
    SPLIT_BY_SIMILARITY = False      # Set to True to enable splitting testing/training data by similarity
    SIMILARITY_THRESHOLD = 0.95      # Threshold to consider two samples as similar. If the similarity is above this threshold, the samples are considered similar.
    MAX_TEST_SIZE_REDUCTION = 0.95   # Max size reduction for the test set; used to ensure that the test set is not too small
    CAT_COLS = ['Stage', 
        'ParentCategories_ParentCategory',
        'ParentCategories_PrimaryCategoryName',
        'Parameters_Parameter_Ownership',
        'Parameters_Parameter_Structures',
        'Parameters_Parameter_WorkType',
    ]

    NUM_COLS = ['Valuation_Value']  # Numerical columns for encoding

    TEXT_COLS = ['Addresses_Address',
                'Details_Detail_Notes',
                'Details_Detail_Scope',
                'DocumentAvailability_Addenda',
                'DocumentAvailability_Plans',
                'DocumentAvailability_Specs',
                'Materials_Material',
                'RSMeansMaterialDivisions_Division_Finishes',
                'RSMeansMaterialDivisions_Division_Masonry',
                'RSMeansMaterialDivisions_Division_Metals',
                'RSMeansMaterialDivisions_Division_Openings',
                'RSMeansMaterialDivisions_Division_ThermalandMoistureProtection',
                ]

    COLUMN_TYPES = { 
        "cat_cols": CAT_COLS,
        "num_cols": NUM_COLS,
        "text_cols": TEXT_COLS
    }

    # OUTPUT DATA PARAMETERS
    DATA_OUTPUT_FILENAME = 'tuning_pipeline/data/cleaned_data'  # Filename suffix for the preprocessed data
    FORMATTED_DATA_OUTPUT_FILENAME = 'tuning_pipeline/data/formatted_data'  # Filename suffix for the formatted data for tuning 
    MODEL_OUTPUT_BQ_DATASET = 'tuned_model_performances'

    # FORMATTING TUNING DATA PARAMETERS
    PROMPT = RELEVANCE_PROMPT

    # TUNING PARAMETERS
    MODEL_DISPLAY_NAME = 'tuned-model'  # display name for the tuned model
    BASE_MODEL_NAME = 'gemini-2.0-flash'  # Base model name for tuning
    EPOCHS = 10
    ADAPTER_SIZE = 4

    # EVALUATION PARAMETERS
    LABELS = ['Very High', 'High', 'Moderate', 'Very Low', 'Low', 'Not Relevant']   # Relevance labels 

    args = { 
        "project_id": PROJECT_ID,
        "location": LOCATION,
        "bucket": BUCKET,

        "dm_instance_url": DM_INSTANCE_URL,

        "id_col": ID_COL,
        "search_id_col": SEARCH_ID_COL,
        "search_name_col": SEARCH_NAME_COL,
        "query_col": QUERY_COL,
        "territory_id_col": TERRITORY_ID_COL,
        "territory_distance_col": TERRITORY_DISTANCE_COL,
        "materials_valuation_col": MATERIALS_VALUATION_COL,
        "response_col": RESPONSE_COL,

        'bq_dataset': BQ_DATASET,
        "cc_bq_table": CC_BQ_TABLE,
        "dodge_bq_table": DODGE_BQ_TABLE,
        "ranking_cols_bq_table": RANKING_COLS_BQ_TABLE,
        "boolean_filters_bq_table": BOOLEAN_FILTERS_BQ_TABLE,
        "territories_bq_table": TERRITORIES_BQ_TABLE,
        "search_product_map_bq_table": SEARCH_PRODUCT_MAP_BQ_TABLE,
        "consolidated_projects_bq_table": CONSOLIDATED_PROJECTS_BQ_TABLE,
        "coalesced_projects_bq_table": COALESCED_PROJECTS_BQ_TABLE,

        "sales_project_id": SALES_PROJECT_ID,
        "sales_bq_dataset": SALES_BQ_DATASET,
        "sales_table": SALES_TABLE,
        "sales_customer_table": SALES_CUSTOMER_TABLE,
        "historical_days": HISTORICAL_DAYS,

        "max_sample_size": MAX_SAMPLE_SIZE,
        "clustering": CLUSTERING,
        "clustering_inf": CLUSTERING_INF,

        "sentence_transformer_name": SENTENCE_TRANSFORMER_NAME,

        "max_diff": MAX_DIFF, 
        "seed": SEED,
        "training_split": TRAINING_SPLIT,
        "validation_split": VALIDATION_SPLIT,
        "split_by_similarity": SPLIT_BY_SIMILARITY,
        "similarity_threshold": SIMILARITY_THRESHOLD,
        "max_test_size_reduction": MAX_TEST_SIZE_REDUCTION,
        "column_types": COLUMN_TYPES,

        "data_output_filename": DATA_OUTPUT_FILENAME,
        "formatted_data_output_filename": FORMATTED_DATA_OUTPUT_FILENAME,
        "model_output_bq_dataset": MODEL_OUTPUT_BQ_DATASET,

        "prompt": PROMPT,

        "model_display_name": MODEL_DISPLAY_NAME,
        "base_model_name": BASE_MODEL_NAME,
        "epochs": EPOCHS,
        "adapter_size": ADAPTER_SIZE,

        "labels": LABELS,
    }

    if env_file == ".env.DEV":
        env = "dev"
    else: 
        env = "prod"
    filename = f'configs/{env}_a_{ADAPTER_SIZE}_e_{EPOCHS}.json'
    with open(filename, 'w') as f:
        json.dump(args, f, indent=4)

    print(filename)

if __name__ == "__main__":
    setup_args()