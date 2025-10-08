
from google.cloud import secretmanager
from typing import TypeVar, Type 
import jsonlines
from enum import Enum 
from pydantic import BaseModel 
from google.cloud import storage
import json 
import pandas as pd
from tqdm import tqdm

# Enums for structured Generation
class ProjectSearchAssignment(Enum): 
    YES = "YES" 
    NO = "NO"

class ProjectSearchAssignmentResult(BaseModel): 
    Project_related_to_Search: ProjectSearchAssignment 
    ProjectID: int 
    SEARCH: str
    Reasoning: str

T = TypeVar("T")

def prompt_v1(gemini_client, model_id, cc_project_json, search_name, search_query, response_type=Type[T]):

    prompt = f"""
    
    **Role:** You are an AI assistant specialized in analyzing construction project data.

    **Objective:** Determine if a given ConstructConnect project (provided as JSON) is relevant to a specific Search Name by evaluating a set of boolean filters against the project's details and **assessing overall context**. 

    **Instructions: Think step-by-step and formulate your logic:**
        1. **Carefully analyze the provided JSON data** representing ConstructConnect project to understand relevant fields and data.

        2. **Analyze the Boolean filters logic** corresponding to the **Search**. 

        3. **Evaluate the project details against the Boolean filters:** 
            a. Determine if the project technically matches the boolean filter logic. Identify the specific terms that caused the match. 
            b. **Assess the context and significance of the matches**. How is the matched term being used in the project? Does the term appear in the primary scope of work or core specifications?
            c. **Consider the overall project focus**. Is the matched concept a major component of the project, or a minor part?

        4. **Formulate Reasoning:** Construct a clear and concise explanation for your decision.

        5. **Respond as YES or NO with a reason for your answer in a valid ProjectSearchAssignmentResult Object**. **RETURN ONLY THE ProjectSearchAssignmentResult Object.**

    **JSON Project Data:** {cc_project_json}

    **Search:**
    {search_name}
   
    **Search Boolean Filters:**
    {search_query}

    **Example Outputs:**
    [
        {{"ProjectID": 1000219, "SEARCH": "Ceilings", "Project_related_to_Search": "YES", "Reasoning": "Reasoning for related response."}}
        {{"ProjectID": 1000220, "SEARCH": "Insulation", "Project_related_to_Search": "NO", "Reasoning": "Reasoning for related response"}} 
    ]
    
    """

    generation_config = { 
        "temperature": 0.7, 
        "candidate_count": 1,
        "max_output_tokens": 2048,
        "response_mime_type": "application/json", 
        "response_schema": ProjectSearchAssignmentResult
    }

    # Generate content using the model
    response = gemini_client.models.generate_content(
        model = model_id,
        contents=prompt, 
        config = generation_config,
    )

    return response.text.strip()

# ---------------------------------------------------------------------------------------

def download_blob(bucket_name, source_blob_name, destination_file_name):
    """Downloads a blob from the bucket."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(source_blob_name)
    blob.download_to_filename(destination_file_name)

def access_secret_version(project_id, secret_name, version_id="latest"):
    """
    Access the secret value from Google Secret Manager.
    """
    # Create the Secret Manager client
    client = secretmanager.SecretManagerServiceClient()

    # Build the resource name of the secret version
    name = f"projects/{project_id}/secrets/{secret_name}/versions/{version_id}"

    # Access the secret version
    response = client.access_secret_version(request={"name": name})

    # Return the secret payload
    return response.payload.data.decode("UTF-8")

def create_stratified_sample(project_df_labeled, n_yes, n_no):

    # Initialize an empty DataFrame to store the sampled rows
    sampled_df = pd.DataFrame()

    # Sample 10 YES and 10 NO rows for each search
    for search in project_df_labeled['SEARCH'].unique(): 

        # Fetch the rows for the current search
        search_df = project_df_labeled[project_df_labeled['SEARCH'] == search]

        # Fetch rows with YES and NO labels
        yes_rows = search_df[search_df['True_Search_Label'] == 'YES']
        no_rows = search_df[search_df['True_Search_Label'] == 'NO']

        if len(yes_rows) > n_yes:
            sample_yes = yes_rows.sample(n=n_yes, random_state=42) 
        else: 
            sample_yes = yes_rows
        if len(no_rows) > n_no:
            sample_no = no_rows.sample(n=n_no, random_state=42)
        else: 
            sample_no = no_rows

        # Concatenate the sampled rows to the sampled_df
        sampled_df = pd.concat([sampled_df, sample_yes, sample_no], ignore_index=True)

    return sampled_df



# Convert project JSON to a structured format and generate and save responses from LLM
def process_and_save_prompt_output(gemini_client, model_id, prompt_function, 
                                   df, searches_df, query_column, output_filename): 

    # Add correct query column to df 
    searches_df = searches_df[['SEARCH', query_column]]
    df = df.merge(searches_df, how = 'left', on = 'SEARCH')
    df.rename(columns={query_column: 'Query'}, inplace=True)
    
    responses = []
    for _, row in tqdm(df.iterrows(), total = len(df)):

        # Find matching search terms
        search_name = row['SEARCH']
        search_query = row['Query']
        row = row.drop(['SEARCH', 'Query'])  # Drop search-related columns for processing
        
        # Convert row to JSON
        row_json_str = row.to_json()
        cc_project_json_record = json.loads(row_json_str)

        # Fetch relevancy from LLM 
        llm_output = prompt_function(gemini_client, model_id, cc_project_json_record, search_name, search_query)
        llm_output = llm_output.replace("```json", "").replace("```", "").strip()

        try: 
            json_output = json.loads(llm_output)
            responses.append(json_output)
        except Exception as e: 
            print(f"Error decoding JSON: {e}")
            continue
            
    with jsonlines.open(output_filename, 'w') as writer:
        writer.write_all(responses)

# Convert a saved JSONL file to dataframe
def jsonl_to_df(filepath): 

    with open(filepath, 'r') as f:
        lines = f.readlines()

    data = [] 
    for line in lines: 
        try: 
            line = line.replace("[", "").replace("]", "").strip()  # Clean up the line
            json_data = json.loads(line)
            project_id = json_data['ProjectID']
            search = json_data['SEARCH']
            related = json_data['Project_related_to_Search']
            reasoning = json_data['Reasoning']
            data.append([project_id, search, related, reasoning])
        except Exception as e:
            print(f"Error decoding JSON: {e}")
            print(f"Problematic line: {line}")
            continue

    df = pd.DataFrame(data, columns=['ProjectID', 'SEARCH', 'Project_related_to_Search', 'Reasoning'])
    return df


# def prompt_v2(cc_project_json, search_name, search_query):
#     prompt = f"""

#         **Objective:** Determine if the provided ConstructConnect project (JSON) is relevant to the given Search, based on specific Boolean filters.

#         **Instructions:**

#         1.  **Understand the Project Data:**
#             * Analyze the provided JSON data**: Analyze the ConstructConnect details and relevant fields.

#         2.  **Interpret the Boolean Filters:**.

#             * First, identify `OR` operations:  The project is related if **at least one** of the conditions separated by `OR` is **strictly** met. For example, in `A OR B OR C`, the project is related if A is true, OR B is true, OR C is true.
#             * Next, identify `NEAR` operations: The project is related if **both** terms are present in the same text field and are close to each other. Finding only `term1` or only `term2` is **NOT sufficient** to satisfy a `NEAR` condition. **BOTH** must be present in literal terms. Do not use outside knowledge about product types.
#             * Next, Identify phrases: Phrases in quotes are treated as single units. **Exact words or sequence of words** must be present. Do not use substrings or partial matches. 
#             * Next, Identify nesting and grouping: Parentheses `(` and `)` are used to group conditions. Do not exceed the scope of the parentheses. For example, in `(A NEAR B) OR (C NEAR D)`, the project will not be related if 'C' is near 'A', but 'C' is not near 'D'. 
        
#         3.  **Evaluate Project Against Filters:**

#             * Systematically evaluate the project details against the Boolean Filter. Capitalization and pluralization generally do not matter unless explicitly stated otherwise, but the *words themselves* must match.
#             * **Base the evaluation solely on the literal text** present in the project JSON and the strict rules defined by the Boolean Filter operators (`OR`, `NEAR`, phrases).
#             * Do NOT use outside knowledge, assumptions, or interpretations beyond the provided text.
#             * If none of the conditions are met, the project is not related to the search. If any condition is met, the project is related to the search.

#         4.  **Format Output:**
#             * **Respond as YES or NO with a reason for your answer in a valid **ProjectSearchAssignmentResult Object** as provided in the Example Output below. **RETURN ONLY THE ProjectSearchAssignmentResult Object**

#         **JSON Project Data:**
#         {cc_project_json}

#         **Search Name:**
#         {search_name}

#         **Search Boolean Filters:**
#         {search_query}

#         **Example Outputs**
#         [
#             {{"ProjectID": 12345, "SEARCH": "Ceilings", "Project_related_to_Search": "YES", "Reasoning": "The project contains the "usg brand acoustic wall panels" in the details. This fulfills the condition ('acoustic wall panel' NEAR "usg") of the boolean filter for "Ceiling"."}}
#             {{"ProjectID": 1000220, "SEARCH": "Insulation", "Project_related_to_Search": "NO", "Reasoning": "There is no information present in any of the project fields that fulfills the filter."}} 
#         ]
#         """
    
#     response = model.generate_content([prompt])
#     return response.text