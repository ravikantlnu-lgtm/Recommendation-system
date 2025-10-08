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
    prompt = f"""

     **Objective:** Classify ConstructConnect projects as very high, high, moderate, low, very low, or not relevant.

        **Instructions:**

        1. **Analyze the provided JSON data:** Understand the project details, including relevant fields and data points. The JSON data representing ConstructConnect project is provided in **Project Data**.

        2. **Utilize Search Terms:** Identify relevant products, materials, and phrases. The search terms are provided in the **Search Terms** section.

        3. **Consider Project Types:** Identify project type. Determine if the project is specialized and has high opportunity for work and visibility. 
        Examples of specialized projects are: 
            * Hospital and health services
            * Churches
            * Commercial real estate
            * Large residential apartments/dormitories
            * University/College buildings
            * Auditoriums
            * Senior living homes
        Examples of non-specialized projects with very low priority are:
            * One-time projects
            * Small residential projects
            * Golf courses

        4. **Identify Building Type**: Identify building type, including interior complexity and specialized work. 

        5. **Identify Locations and Distance:** Identify the project location and distance from nearest branch. Consider if a branch is too far away from a location. 
        Urban areas should have closer branches, while rural areas can have branches further away.

        6. **Identify Associated Brands:** Identify associated brands to the product. Associated brands include: 
            * Armstrong Ceilings 
            * Sto 
            * Dryvit

        7. **Identify Available Plans:** Identify if the project has detailed and available plans and specs.

        8. **Classify Projects:**
            a. Prioritize projects based on how relevant the inputs are to the search terms.
            b. Next, prioritize projects based on the project type, as specified in the previous steps. Deprioritize non-specialized projects. 
            c. Next, prioritize building types based on how complex the interior work is, as specified in the previous steps. Deprioritize projects with little interior work.
            d. Next, prioritize projects that have reasonable distance to the nearest branch, as specified in the previous steps. Deprioritize projects that are too far away from a branch.
            e. Next, prioritize projects that have associated brands, as specified in the previous steps. Lack of associated brands will not lower the priority.
            f. Next, increase priority if the project has detailed plans and specs. Lack of plans and specs will not lower the priority. 
            g. When other factors are equal, prioritize higher-value projects (e.g., higher total dollar amount).

        8. **Estimate Relevancy:** Estimate the relevancy of each project based on the above factors and total dollar amount.
        9. **Respond in ProjectClassification Object Format** as VERY_HIGH, HIGH, MODERATE, LOW, VERY_LOW, NOT_RELEVANT with a reason for your answer in a valid **ProjectClassification object** as provided in the Example Output below. **RETURN ONLY THE ProjectClassification Object**

        **Input Data:**
            **Project Data:**
            {cc_project_json}

            **Search**
            {search}

            **Boolean Filter**
            {search_terms}

        **Example Output:**
         [
          
          {{"Relevance": "Not Relevant", "Reasoning": "The project details and materials do not contain any mention of the search terms. Therefore, it is not relevant."}} 
          {{"Relevance": "Very High", "Reasoning": "Project mentions 'roofing materials", "concrete", "fry", and "steel", matching our search terms. The project is commercial, has high visibility, and opportunity for specialized work."}}
          {{"Relevance": "Low", "Reasoning": "Project has some search terms in the description such as "steel". The project will require little interior work and is a one-time job."}}
          {{"Relevance": "Moderate", "Reasoning": "Project mentions 'steel beams' and 'concrete mix,' matching our search terms "STEEL" and "CONCRETE". The project has moderate valuation."}}
          {{"Relevance": "High", "Reasoning": "Project mentions 'steel beams," "concrete," and "gysum," matching many of the provided search terms. The project has high dollar valuation and will require higher specs. "}}
          
        ]

        """
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
    prompt = f"""

     **Objective:** Classify ConstructConnect projects as very high, high, moderate, low, very low, or not relevant.

        **Instructions:**

        1. **Analyze the provided JSON data:** Understand the project details, including relevant fields and data points. The JSON data representing ConstructConnect project is provided in **Project Data**.

        2. **Utilize Search Terms:** Identify relevant products, materials, and phrases. The search terms are provided in the **Search Terms** section.

        3. **Consider Project Types:** Identify project type. Determine if the project is specialized and has high opportunity for work and visibility. 
        Examples of specialized projects are: 
            * Hospital and health services
            * Churches
            * Commercial real estate
            * Large residential apartments/dormitories
            * University/College buildings
            * Auditoriums
            * Senior living homes
        Examples of non-specialized projects with very low priority are:
            * One-time projects
            * Small residential projects
            * Golf courses

        4. **Identify Building Type**: Identify building type, including interior complexity and specialized work. 

        5. **Identify Locations and Distance:** Identify the project location and distance from nearest branch. Consider if a branch is too far away from a location. 
        Urban areas should have closer branches, while rural areas can have branches further away.

        6. **Identify Associated Brands:** Identify associated brands to the product. Associated brands include: 
            * Armstrong Ceilings 
            * Sto 
            * Dryvit

        7. **Identify Available Plans:** Identify if the project has detailed and available plans and specs.

        8. **Classify Projects:**
            a. Prioritize projects based on how relevant the inputs are to the search terms.
            b. Next, prioritize projects based on the project type, as specified in the previous steps. Deprioritize non-specialized projects. 
            c. Next, prioritize building types based on how complex the interior work is, as specified in the previous steps. Deprioritize projects with little interior work.
            d. Next, prioritize projects that have reasonable distance to the nearest branch, as specified in the previous steps. Deprioritize projects that are too far away from a branch.
            e. Next, prioritize projects that have associated brands, as specified in the previous steps. Lack of associated brands will not lower the priority.
            f. Next, increase priority if the project has detailed plans and specs. Lack of plans and specs will not lower the priority. 
            g. When other factors are equal, prioritize higher-value projects (e.g., higher total dollar amount).

        9. **Estimate Relevancy:** Estimate the relevancy of each project based on the above factors and total dollar amount.

        10. **Confidence Score**: Provide a confidence score between 0.0 (Low Confidence) and 1.0 (High Confidence) reflecting your certainty in the assigned **Relevance Score**.
            * **Base this confidence primarily on the clarity, completeness, and consistency of the input information** used to evaluate the factors in Step 8.
            * **Calibration Guide:**
                * **> 0.9:** Reserve for cases where **ALL critical factors** are evaluated using **explicit, complete, and unambiguous** input data. Inputs strongly support the relevance score.
                * **0.7 - 0.9:** Use when most factors (including critical ones) are clear, but perhaps some **secondary information** is inferred/missing, or there's **very minor ambiguity** that doesn't significantly impact the overall relevance assessment.
                * **0.3 - 0.6:** Use when **one or more critical factors** rely partially on **inference, contain some ambiguity, or have missing details**, OR if multiple secondary factors are uncertain. The relevance score is plausible but not definitive.
                * **< 0.3:** Use when there is **significant missing information, ambiguity, or contradiction** affecting **one or more critical factors**, making the calculated Relevance Score highly speculative or uncertain.

        11. **Respond in ProjectClassificationConfidenceInterval Object Format** as VERY_HIGH, HIGH, MODERATE, LOW, VERY_LOW, NOT_RELEVANT with a reason and confidence for your answer in a valid **ProjectClassificationConfidenceInterval object** as provided in the Example Output below.
            **RETURN ONLY THE ProjectClassificationConfidenceInterval Object**

        **Input Data:**
            **Project Data:**
            {cc_project_json}

            **Search**
            {search}

            **Boolean Filter**
            {search_terms}

        **Example Output:**
         [
          
          {{"Relevance": "Not Relevant", "Reasoning": "The project details and materials do not contain any mention of the search terms. Therefore, it is not relevant.", "Confidence": Confidence}} 
          {{"Relevance": "Very High", "Reasoning": "Project mentions 'roofing materials", "concrete", "fry", and "steel", matching our search terms. The project is commercial, has high visibility, and opportunity for specialized work.", "Confidence": Confidence}}
          {{"Relevance": "Low", "Reasoning": "Project has some search terms in the description such as "steel". The project will require little interior work and is a one-time job.", "Confidence": Confidence}}
          {{"Relevance": "Moderate", "Reasoning": "Project mentions 'steel beams' and 'concrete mix,' matching our search terms "STEEL" and "CONCRETE". The project has moderate valuation.", "Confidence": Confidence}}
          {{"Relevance": "High", "Reasoning": "Project mentions 'steel beams," "concrete," and "gysum," matching many of the provided search terms. The project has high dollar valuation and will require higher specs. ", "Confidence": Confidence}}
          
        ]

        """
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

    prompt = f"""

      **Objective:** Generate the reasoning for a **given** ConstructConnect project relevance classification.

      **Instructions:**

      1.  **Analyze the provided JSON data:** Understand the project details, including relevant fields and data points. The JSON data representing the ConstructConnect project is provided in **Project Data**.
      2.  **Utilize Search Terms:** Identify mentions of relevant products, materials, and phrases within the project data. The search terms are provided in the **Search Terms** section and potentially refined in the **Search** section.
      3.  **Consider Project Types:** Identify the project type. Note if it's a specialized type with high opportunity (e.g., Hospital, University, Commercial Real Estate, Large Residential) or a lower priority type (e.g., small residential, one-time jobs).
      4.  **Identify Building Type**: Identify the building type and infer the potential interior complexity and need for specialized work based on it.
      5.  **Identify Locations and Distance:** Note the project location and its distance from the nearest branch (if provided or inferable). Consider the implications of distance (urban vs. rural context).
      6.  **Identify Associated Brands:** Check for mentions of specific associated brands like Armstrong Ceilings, Sto, Dryvit.
      7.  **Identify Available Plans:** Note if detailed plans and specifications are mentioned as being available.
      8.  **Analyze Project Value:** Consider the total dollar amount or valuation of the project.

      9.  **Generate Reasoning:** Based on your analysis of the factors above (Steps 1-8) and the **provided Relevance Classification**, formulate a concise reasoning statement. This statement must explain *why* the project aligns with the given classification by connecting specific project details (e.g., presence/strength of search term matches, project type suitability, building complexity, location factors, associated brands, plan availability, project value) to justify the **provided** relevance level.

      10. **Confidence Score**: Provide a confidence score between 0.0 (Low Confidence) and 1.0 (High Confidence) reflecting your certainty in the assigned **Relevance Score** and your Reasoning.
        * **Base this confidence primarily on the clarity, completeness, and consistency of the input information** used to generate reasoning in steps 1-8.
        * **Calibration Guide:**
            * **> 0.9:** Reserve for cases where **ALL critical factors** are evaluated using **explicit, complete, and unambiguous** input data.
            * **0.7 - 0.9:** Use when most factors (including critical ones) are clear, but perhaps some **secondary information** is inferred/missing, or there's **very minor ambiguity**.
            * **0.3 - 0.6:** Use when **one or more critical factors** rely partially on **inference, contain some ambiguity, or have missing details**, OR if multiple secondary factors are uncertain.
            * **< 0.3:** Use when there is **significant missing information, ambiguity, or contradiction** affecting **one or more critical factors**, making the calculated Relevance and reasoning highly speculative or uncertain.


      11. **Respond in ProjectClassification Object Format:** Output a single valid JSON **ProjectClassification object** containing the *provided* `Relevance` (matching the input Relevance Classification) and your generated `Reasoning`. **RETURN ONLY THE ProjectClassification Object**.

      **Input Data:**
          **Project Data:**
          {json.dumps(cc_project_json)} # Ensure JSON is properly formatted string

          **Search:**
          {search}

          **Boolean Filter / Search Terms:**
          {search_terms}

          **Provided Relevance Classification:**
          {relevance_classification}
    """

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
