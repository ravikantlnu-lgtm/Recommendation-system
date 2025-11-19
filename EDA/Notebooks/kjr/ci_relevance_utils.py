import json
import os
import sys
from enum import Enum
from typing import TypeVar

import jsonlines
import pandas as pd
from google.cloud import secretmanager
from pydantic import BaseModel, confloat
from tqdm import tqdm

T = TypeVar("T")

current_script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(
    os.path.join(current_script_dir, os.pardir, os.pardir, os.pardir)
)
cloud_function_dir = os.path.join(project_root, "CloudFunction/utils")
sys.path.insert(0, cloud_function_dir)

from prompts import (
    CI_REASONING_PROMPT,
    CI_RELEVANCE_PROMPT_V1,
    CI_RELEVANCE_PROMPT_V2,
)
from relevance_prompt_examples import RELEVANCE_PROMPT_EXAMPLES


class ProjectRelevanceBoolean(Enum):
    VERY_HIGH = "very high"
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    VERY_LOW = "very low"
    NOT_RELEVANT = "not relevant"


class ProjectClassification(BaseModel):
    Relevance: ProjectRelevanceBoolean
    Reasoning: str


class ProjectClassificationConfidenceInterval(BaseModel):
    Relevance: ProjectRelevanceBoolean
    Reasoning: str
    Confidence: confloat(ge=0, le=1)


def get_secret(project_number: str, secret_name: str):
    client = secretmanager.SecretManagerServiceClient()
    secret_version_name = (
        f"projects/{project_number}/secrets/{secret_name}/versions/latest"
    )
    response = client.access_secret_version(request={"name": secret_version_name})

    return response.payload.data.decode("utf-8")


# Original assign_relevance prompt with option for few-shot examples
def relevance_prompt_v1(
    gemini_client: object,
    model_id: str,
    cc_project_json: str,
    search: str,
    search_terms: str,
    relevance_examples: dict = RELEVANCE_PROMPT_EXAMPLES,
):
    prompt = CI_RELEVANCE_PROMPT_V1.format(
        cc_project_json=cc_project_json,
        search=search,
        search_terms=search_terms,
    )
    if relevance_examples:
        examples_prompt = ""

        # Get list of examples based on search name
        search_examples = None

        # Iterate through the keys of the examples dictionary
        for key, examples_list in relevance_examples.items():
            # Check if the current key is a substring of the search
            if key.lower() in search.lower():
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
                            {search}

                            **Boolean Filter**
                            {boolean_filter_example}

                        **Output:**
                            {json.dumps(output_example, indent=4)}
                    """
        else:
            print(f"No examples found for search: {search}")

        if examples_prompt:
            prompt += examples_prompt

    generation_config = {
        "temperature": 0,
        "candidate_count": 1,
        "max_output_tokens": 2048,
        "seed": 42,
        "top_k": 1,
        "frequency_penalty": 0,
        "presence_penalty": 0,
        "response_mime_type": "application/json",
        "response_schema": ProjectClassification,
    }

    response = gemini_client.models.generate_content(
        model=model_id, contents=prompt, config=generation_config
    )

    return response.text.strip()


# Original assign_relevance prompt with option for few-shot examples
def relevance_prompt_v2(
    gemini_client: object,
    model_id: str,
    cc_project_json: str,
    search: str,
    search_terms: str,
    relevance_examples: dict = RELEVANCE_PROMPT_EXAMPLES,
):
    prompt = CI_RELEVANCE_PROMPT_V2.format(
        cc_project_json=cc_project_json,
        search=search,
        search_terms=search_terms,
    )
    if relevance_examples:
        examples_prompt = ""

        # Get list of examples based on search name
        search_examples = None

        # Iterate through the keys of the examples dictionary
        for key, examples_list in relevance_examples.items():
            # Check if the current key is a substring of the search
            if key.lower() in search.lower():
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

                    # Add confidence to output example
                    output_example["Confidence"] = 1.0

                    examples_prompt += f""" 
                    
                    **Example {idx + 1}:**

                        **Input Data:**

                            **Project Data:**
                            {json.dumps(project_data_example, indent=4)}

                            **Search**
                            {search}

                            **Boolean Filter**
                            {boolean_filter_example}

                        **Output:**
                            {json.dumps(output_example, indent=4)}
                    """
        else:
            print(f"No examples found for search: {search}")

        if examples_prompt:
            prompt += examples_prompt

    generation_config = {
        "temperature": 0,
        "candidate_count": 1,
        "max_output_tokens": 2048,
        "seed": 42,
        "top_k": 1,
        "frequency_penalty": 0,
        "presence_penalty": 0,
        "response_mime_type": "application/json",
        "response_schema": ProjectClassificationConfidenceInterval,
    }

    response = gemini_client.models.generate_content(
        model=model_id, contents=prompt, config=generation_config
    )

    return response.text.strip()


def process_and_save_prompt_output(
    gemini_client,
    model_id: str,
    prompt_function: callable,
    df: pd.DataFrame,
    search_col: str,
    query_col: str,
    relevance_col: str,
    reasoning_col: str,
    output_filename: str,
):
    """
    This function processes a DataFrame of project data, generates the relevance from the LLM, and saves the results to a JSONL file.
    Args:
        gemini_client (object): Gemini client for LLM interaction.
        model_id (str): Model ID for the LLM.
        prompt_function (callable): Function to generate the prompt.
        df (pd.DataFrame): DataFrame containing the project data.
        search_col (str): Column name for the search term.
        query_col (str): Column name for the query.
        output_filename (str): Filename to save the output JSONL file.
    Returns:
        None
    """

    responses = []
    df = df.drop([relevance_col, reasoning_col], axis=1)
    for _, row in tqdm(df.iterrows(), total=len(df)):

        # Find search, query, and project_id
        search_name = row[search_col]
        search_query = row[query_col]
        project_id = row["ProjectID"]
        row = row.drop([search_col, query_col])

        # Convert row to JSON
        row_json_str = row.to_json()
        cc_project_json_record = json.loads(row_json_str)

        # Fetch relevancy from LLM
        llm_output = prompt_function(
            gemini_client=gemini_client,
            model_id=model_id,
            cc_project_json=cc_project_json_record,
            search=search_name,
            search_terms=search_query,
        )

        llm_output = llm_output.replace("```json", "").replace("```", "").strip()

        try:
            json_output = json.loads(llm_output)
            json_output["ProjectID"] = project_id  # Add project_id to response
            responses.append(json_output)
        except Exception as e:
            print(f"Error decoding JSON: {e}")
            responses.append({})  # Append empty dict if error occurs

    # Write out responses to JSONL file
    with jsonlines.open(output_filename, "w") as writer:
        writer.write_all(responses)


def jsonl_to_df(filepath):

    with open(filepath, "r") as f:
        lines = f.readlines()

    data = []
    for line in lines:
        try:
            line = line.replace("[", "").replace("]", "").strip()  # Clean up the line
            json_data = json.loads(line)

            # Fetch the relevant fields
            project_id = json_data["ProjectID"]
            relevance = json_data["Relevance"]
            reasoning = json_data["Reasoning"]
            confidence = json_data.get("Confidence", None)
            if confidence:
                confidence = float(confidence)

            # Add to the data list
            data.append([project_id, relevance, reasoning, confidence])
        except Exception as e:
            print(f"Error decoding JSON: {e}")
            print(f"Problematic line: {line}")
            data.append([None, None, None, None])
            continue

    # Create a DataFrame from the data list
    df = pd.DataFrame(
        data, columns=["ProjectID", "Relevance", "Reasoning", "Confidence"]
    )
    return df


def reasoning_prompt_v1(
    gemini_client: object,
    model_id: str,
    cc_project_json: str,
    search: str,
    search_terms: str,
    relevance_classification: str,
):

    prompt = CI_REASONING_PROMPT.format(
        cc_project_json=json.dumps(cc_project_json),
        search=search,
        search_terms=search_terms,
        relevance_classification=relevance_classification,
    )

    generation_config = {
        "temperature": 0,
        "candidate_count": 1,
        "max_output_tokens": 2048,
        "seed": 42,
        "top_k": 1,
        "frequency_penalty": 0,
        "presence_penalty": 0,
        "response_mime_type": "application/json",
        "response_schema": ProjectClassificationConfidenceInterval,
    }

    response = gemini_client.models.generate_content(
        model=model_id, contents=prompt, config=generation_config
    )
    return response.text.strip()
