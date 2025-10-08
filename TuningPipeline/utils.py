# Utilities

import json
import pandas as pd 
import logging 
import os 
from google.cloud import storage, aiplatform, secretmanager
from google.api_core import exceptions
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sentence_transformers import SentenceTransformer
import nltk 
from nltk.corpus import stopwords 
from nltk.stem import PorterStemmer
from nltk import word_tokenize
import pandas_gbq

import re 
import string
from typing import List

import relevance_prompt_examples

def access_secret_version(project_id: str, secret_id: str, version_id: str = "latest"): 
    """ 
    Access the payload from a secretID from Google Cloud Secret Manager. 

    Args: 
        project_id (str): The GCP project ID.
        secret_id (str): The ID of the secret to access.
        version_id (str): The version of the secret to access. Default is "latest".
    Returns:
        str: The secret as a string. 
    """

    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

def setup_logging(level=logging.INFO):
    logging.basicConfig(level=level, format='%(asctime)s - %(levelname)s - %(message)s')
    logging.info(f"Logging setup complete with level: {logging.getLevelName(level)}")

def init_vertex(project_id: str, location: str, experiment_name: str = None, run_id: str = None):
    logging.info(f"Initializing Vertex AI with project_id: {project_id}, location: {location}")
    aiplatform.init(project=project_id, location=location, experiment=experiment_name)
    if experiment_name:
        logging.info(f"Experiment set: {experiment_name}")
    if run_id:
        logging.info(f"Starting run with ID: {run_id}")
        aiplatform.start_run(run_id)
    logging.info("Vertex AI initialization complete")

def upload_file_to_gcs(local_file_path: str, bucket_name: str, blob_name: str) -> str:
    """
    Upload a file to Google Cloud Storage.

    This function uploads a local file to a specified GCS bucket and path.

    Args:
        local_file_path (str): The path to the local file to upload.
        bucket_name (str): The name of the GCS bucket.
        blob_name (str): The name of the blob (file) in GCS.

    Returns:
        str: The GCS URI of the uploaded file.

    Raises:
        GoogleAPIError: If there's an error during the upload process.

    Example:
        gcs_uri = upload_file_to_gcs("/local/path/file.csv", "my-bucket", "path/to/file.csv")
    """
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(local_file_path)
        gcs_uri = f"gs://{bucket_name}/{blob_name}"
        logging.info(f"File uploaded successfully. GCS URI: {gcs_uri}")
        return gcs_uri
    except exceptions.GoogleAPIError as e:
        logging.error(f"Error uploading to GCS: {e}", exc_info=True)
        raise

def download_file_from_gcs(bucket_name: str, blob_name: str, local_file_path: str) -> None:
    """
    Download a file from Google Cloud Storage.

    This function downloads a file from a specified GCS bucket and path to a local file.

    Args:
        bucket_name (str): The name of the GCS bucket.
        blob_name (str): The name of the blob (file) in GCS.
        local_file_path (str): The path where the file should be saved locally.

    Raises:
        GoogleAPIError: If there's an error during the download process.

    Example:
        download_file_from_gcs("my-bucket", "path/to/file.csv", "/local/path/file.csv")
    """
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.download_to_filename(local_file_path)
        logging.info(f"File downloaded successfully to {local_file_path}")
    except exceptions.GoogleAPIError as e:
        logging.error(f"Error downloading from GCS: {e}", exc_info=True)
        raise

def clean_text(text: str, tokenizer: callable, stopwords: set, stemmer: callable) -> str: 
    """
    This function cleans input text for vectorization. 
    Args: 
        text (str): The input text to clean.
        tokenizer (callable): A tokenizer function to tokenize the text.
        stopwords (set): A set of stopwords to remove from the tokens.
        stemmer (callable): A stemmer function to stem the tokens.
    Returns: 
        str: The cleaned text.
    """
    text = str(text).lower()
    text = re.sub(f"[{re.escape(string.punctuation)}]", "", text)  # Remove punctuation
    tokens = tokenizer(text)
    tokens = ["" if t.isdigit() else t for t in tokens]  # Remove digits
    tokens = [token for token in tokens if token not in stopwords]

    if stemmer: 
        tokens = [stemmer.stem(token) for token in tokens]
    
    return ' '.join(tokens)


def encode_df_for_clustering(df: pd.DataFrame, cat_cols: List[str], num_cols: List[str], 
                        text_cols: List[str], sentence_transformer_name: str = 'all-MiniLM-L6-v2') -> pd.DataFrame:

    """
    This function encodes the columns of a dataframe for clustering. 

    It handles categorical, numerical, and text columns by applying appropriate encoding techniques:
    - Categorical columns: One-hot encoding
    - Numerical columns: Scaling
    - Text columns: TF-IDF vectorization
    Args: 
        df (pd.DataFrame): The dataframe to encode.
        cat_cols (list): A list of categorical column names.
        num_cols (list): A list of numerical column names.
        text_cols (list): A list of text column names.
        sentence_transformer_name (str): The name of the SentenceTransformer model to use for text encoding.
    Returns: 
        pd.DataFrame: The encoded dataframe.
    """

    # Create a new dataframe with the relevant columns
    df_to_cluster = df[cat_cols + num_cols + text_cols]

    # Scale numerical columns
    logging.info("Scaling numerical columns...")
    scaler = StandardScaler()
    scaled_values = scaler.fit_transform(df_to_cluster[num_cols])
    encoded_num_df = pd.DataFrame(scaled_values, columns=num_cols, index=df_to_cluster.index)  # Ensure index alignment
    logging.info("Shape of numerical dataframe: %s", encoded_num_df.shape)

    # Encode categorical columns
    logging.info("Encoding categorical variables with one hot encoding...")
    enc = OneHotEncoder(sparse_output=False) 
    one_hot_enc = enc.fit_transform(df_to_cluster[cat_cols])  # One-hot encode categorical columns
    encoded_cat_df = pd.DataFrame(one_hot_enc, columns=enc.get_feature_names_out(cat_cols), index=df_to_cluster.index)  # Ensure index alignment
    logging.info("Shape of categorical dataframe: %s", encoded_cat_df.shape)

    # Initialize NLP tools
    stop_words = set(stopwords.words('english')) # stopwords to remove 
    tokenizer = word_tokenize
    stemmer = PorterStemmer() # 
    model = SentenceTransformer(sentence_transformer_name, similarity_fn_name='cosine') # SentenceTransformer model

    # Create embeddings for each text column 
    logging.info("Creating embeddings for text columns...")
    encoded_text_df = pd.DataFrame() # Initialize empty dataframe for text embeddings
    for col in text_cols:

        df_with_text_col = df_to_cluster[[col]].copy()
        df_with_text_col.loc[:, col] = df_with_text_col[col].fillna("")
        df_with_text_col.loc[:, col] = df_with_text_col[col].apply(lambda x: clean_text(x, tokenizer, stop_words, stemmer)) # clean text 

        text_embeddings = model.encode(df_with_text_col[col].values) # embed text column into vectors

        df_embeddings = pd.DataFrame(text_embeddings, columns = [f'{col}_embedding_{i}' for i in range(text_embeddings.shape[1])]) # Add embeddings to dataframe 
        encoded_text_df = pd.concat([encoded_text_df, df_embeddings], axis=1)

    encoded_text_df.index = df_to_cluster.index # Ensure index alignment
    logging.info("Shape of text dataframe: %s", encoded_text_df.shape)
    
    # Concatenate all encoded dataframes
    encoded_num_df.reset_index(drop=True, inplace=True)
    encoded_cat_df.reset_index(drop=True, inplace=True)
    encoded_text_df.reset_index(drop=True, inplace=True)
    
    all_encoded_df = pd.concat([encoded_cat_df, encoded_num_df, encoded_text_df], axis=1)
    logging.info(f"Finished encoding data. Dataset shape: {all_encoded_df.shape}")

    return all_encoded_df


def get_project_owner_contacts_cc(
    client,
    project_id: str,
    dataset: str, 
    cc_feed_table: str,
    cc_project_id: str,
    time_created: str, 
):
    """
    Get the contact information for owner of a project using project_id and time_created.
    """

    query = f"""SELECT
        TO_JSON_STRING(
            STRUCT(
                company.Name AS owner_name,
                (
                    SELECT
                        ARRAY_AGG(p.PhoneNumnber)
                    FROM
                        UNNEST(company.Phones.Phone) AS p
                ) AS phone_numbers
            )
        ) AS owner_json
    FROM
        `{project_id}.{dataset}.{cc_feed_table}` t,
        UNNEST(t.Companies) AS company_wrap,
        UNNEST(company_wrap.Company) AS company
    WHERE
        t.ProjectID = {cc_project_id} and t.sourceFileCreationTime = '{time_created}'
        AND INSTR(LOWER(company.ROLE), "owner") > 0 
    """

    try:
        results = pandas_gbq.read_gbq(query, project_id=project_id)
    except Exception as e:
        logging.info(f"Error executing project owner contacts query: {e}")
        return pd.DataFrame()

    return results

def get_project_owner_contacts_dodge(
        client,
        project_id: str,
        dataset: str, 
        dodge_feed_table: str, 
        dodge_project_id: str,
        time_created: str
):
    """Get the contact information for owner of a project using project_id and time_created."""
    query = f"""
    SELECT
        TO_JSON_STRING(
        STRUCT(
            company_details.CompanyName as owner_name,
            [company_details.CompanyTelephone] as phone_numbers 
        )
        ) as owner_json
    FROM
        `{project_id}.{dataset}.{dodge_feed_table}`,
        UNNEST(Companies.Company) AS company_details
    WHERE DRNumber = {dodge_project_id} and sourceFileCreationTime = '{time_created}'
    and INSTR(LOWER(company_details.FactorType), "owner") > 0
    """

    try:
        results = pandas_gbq.read_gbq(query, project_id=project_id)
    except Exception as e:
        logging.info(f"Error executing project owner contacts query: {e}")
        return pd.DataFrame()

    return results


def get_project_owner_contacts(
    client, 
    project_id: str, 
    dataset: str, 
    cc_feed_table: str,
    dodge_feed_table: str,
    primary_project_id: str,
    consolidated_primary_project_view: str, 
):

    contacts_df = pd.DataFrame({"owner_json": []})

    cc_project_query = f"""SELECT ProjectID, sourceFileCreationTime
    FROM `{project_id}.{dataset}.{consolidated_primary_project_view}`
    WHERE primary_project_id = '{primary_project_id}' and candidate_source = "construct_connect" """

    cc_projects = pandas_gbq.read_gbq(cc_project_query, project_id=project_id)

    for _, row in cc_projects.iterrows():
        cc_project_id = row["ProjectID"]
        time_created = row["sourceFileCreationTime"]
        time_created = time_created.strftime("%Y-%m-%dT%H:%M:%S")

        # Fetch contacts for each project
        contacts = get_project_owner_contacts_cc(
            client,
            project_id,
            dataset,
            cc_feed_table,
            cc_project_id, 
            time_created
        )
        contacts_df = pd.concat([contacts_df, contacts], ignore_index=True)

    dodge_project_query = f"""SELECT ProjectID, sourceFileCreationTime
    FROM `{project_id}.{dataset}.{consolidated_primary_project_view}`
    WHERE primary_project_id = '{primary_project_id}' and candidate_source = "dodge" """

    dodge_projects = pandas_gbq.read_gbq(dodge_project_query, project_id=project_id)
    for _, row in dodge_projects.iterrows():
        dodge_project_id = row["ProjectID"]
        time_created = row["sourceFileCreationTime"]
        time_created = time_created.strftime("%Y-%m-%dT%H:%M:%S")

        # Fetch contacts for each project
        contacts = get_project_owner_contacts_dodge(
            client, 
            project_id,
            dataset,
            dodge_feed_table,
            dodge_project_id,
            time_created
        )
        contacts_df = pd.concat([contacts_df, contacts], ignore_index=True)

    print("Fetched contacts from all project owners. Total contacts found: ", len(contacts_df))

    return contacts_df 

def fetch_examples(RELEVANCE_EXAMPLES, search_name): 
    examples_prompt = ""

    # Get list of examples based on search name
    search_examples = None

    # Iterate through the keys of the examples dictionary
    for key, examples_list in RELEVANCE_EXAMPLES.items():
        # Check if the current key is a substring of the search
        if key.lower() in search_name.lower():
            search_examples = examples_list
            break  # Stop after finding the first match

    if search_examples:

        # Iterate through the examples and format them to prompt
        for idx, example in enumerate(search_examples):

            # Fetch the example data
            project_data_example = example.get("Project Data", None)
            search_example = example.get("Search", None)
            boolean_filter_example = example.get("Boolean Filter", None)
            output_example = example.get("Output", None)

            # Add example to prompt if all fields are present and valid
            if (
                isinstance(project_data_example, dict)
                and isinstance(search_example, str)
                and isinstance(boolean_filter_example, str)
                and isinstance(output_example, dict)
            ):

                examples_prompt += f""" 
                
                **Example {idx + 1}:**

                    **Input Data:**

                        **Project Data:**
                        {json.dumps(project_data_example, indent=4)}

                        **Search**
                        {search_name}

                        **Boolean Filter**
                        {boolean_filter_example}

                    **Output:**
                        {json.dumps(output_example, indent=4)}
                """

    return examples_prompt


def row_to_example_input(client, 
                        prompt: str, 
                        project_data: str,
                        primary_project_id: str, 
                        search_name: str, 
                        products: List[str],
                        boolean_filter: str, 
                        territory_name: str, 

                        project_id: str, 
                        dataset: str, 
                        cc_feed_table: str,
                        dodge_feed_table: str,
                        consolidated_primary_leads_view: str, 
                        
                        historical_sales_df: pd.DataFrame,
                        historical_days: int,
                        materials_valuation: float): 

    sales_data_product_location_json = None 
    sales_data_contractor_level_json = None  

    # Fetch sales data with same product and location
    if len(products) > 0 and len(historical_sales_df) > 0:
        sales_data_product_location = historical_sales_df[
            historical_sales_df["product_category_code"].str.lower().isin(
                [product.lower() for product in products])
        ]
        if territory_name: 
            location_filter = historical_sales_df["location"].str.lower().str.contains(territory_name.lower(), na=False)
            sales_data_product_location = sales_data_product_location[location_filter] 
    else: 
        sales_data_product_location = pd.DataFrame()

    # Generate summary statistics of profit for this product and location
    if len(sales_data_product_location) != 0:
        
        sales_data_product_location = sales_data_product_location[["order_id", 
                                                                    "product_category", 
                                                                    "location",
                                                                    "gross_profit"]]

        # Convert product category to lowercase
        sales_data_product_location["product_category"] = (
            sales_data_product_location["product_category"].apply(
                lambda x: x.lower()
            )
        )

        product_summary_dict = {}
        for category in sales_data_product_location["product_category"].unique():
            category_data = sales_data_product_location[sales_data_product_location["product_category"] == category]
            
            # Calculate units sold (count of orders) and average gross profit
            units_sold = len(category_data)
            avg_gross_profit = category_data["gross_profit"].mean()
            
            product_summary_dict[category] = {
                "units_sold": int(units_sold),
                "avg_gross_profit": float(round(avg_gross_profit, 2))
            }
        
        # Convert to a readable string format
        sales_data_product_location_json = json.dumps(product_summary_dict)
        print("Product location sales summary:", sales_data_product_location_json) 
        
    # Fetch historical sales data for contractor level
    phone_numbers = []
    project_owner_contact_information = get_project_owner_contacts(client=client,
                                                                    project_id=project_id,
                                                                    dataset=dataset,
                                                                    cc_feed_table=cc_feed_table,
                                                                    dodge_feed_table=dodge_feed_table,
                                                                    primary_project_id=primary_project_id,
                                                                    consolidated_primary_project_view=consolidated_primary_leads_view) 

    if len(project_owner_contact_information) != 0:
        owner_json_rows = project_owner_contact_information["owner_json"].tolist()
        # Collect phone numbers from the owner information
        for entry in owner_json_rows:
            try:
                owner_dict = json.loads(entry)
                # Add phone number to list 
                if "phone_numbers" in owner_dict and owner_dict["phone_numbers"] is not None:
                    phone_numbers.extend(owner_dict["phone_numbers"])
            except json.JSONDecodeError as e:
                logging.info(f"Error decoding JSON: {e} for entry: {entry}")
                continue

        phone_numbers = [
            re.sub(r"[^0-9]", "", s) for s in phone_numbers
        ]  # Normalize phone numbers by removing non-numeric characters
        phone_numbers = list(set(phone_numbers))  # Remove duplicates

    # Fetch historical data for sales with this contractor
    if len(phone_numbers) > 0:
        sales_data_contractor_level = historical_sales_df[historical_sales_df['phone_number'].isin(phone_numbers)]
    else: 
        sales_data_contractor_level = pd.DataFrame()
        
    if len(sales_data_contractor_level) != 0: 
        # Generate summary statistics of profit for this contractor
        profit_summary_contractor_stats = { 
            "sales_made": int(sales_data_contractor_level[['gross_profit']].count()[0]),
            "avg_gross_profit": float(sales_data_contractor_level[['gross_profit']].mean()[0].round(2)),
        }
        print(profit_summary_contractor_stats)

        sales_data_contractor_level_json = json.dumps(profit_summary_contractor_stats)


    # Fetch examples for the prompt for a specific search
    examples = fetch_examples(relevance_prompt_examples.RELEVANCE_PROMPT_EXAMPLES, search_name)

    # Format the full prompt with the provided data
    full_prompt = prompt.format(
        project_id=primary_project_id,
        project_data=project_data, 
        search=search_name, 
        search_terms=boolean_filter,
        materials_valuation=materials_valuation,
        historical_days=historical_days,
        sales_data_product_location=sales_data_product_location_json,
        sales_data_contractor_level=sales_data_contractor_level_json,
        examples_prompt=examples if examples else ""
    )

    # Add parts to the content for LLM fine-tuning
    parts = [{"text": full_prompt}]

    return parts
