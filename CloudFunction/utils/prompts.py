"""Centralized prompt templates for LLM interactions."""

ASSIGN_PROJECT_SEARCH_PROMPT = """
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

    **Example Output Format:**
        {{
            "Project_related_to_Search": YES/NO,
            "Reasoning": "reason for relation response"
        }}

    """

PROJECT_RELEVANCE_PROMPT = """

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

        4. **Note the Materials Value for the Search:** Identify the valuation relevant materials, which is provided.

        5. **Analyze the Historical Sales Data:** If historical sales data is provided, analyze the statistics to understand past performance.
            Historical data can be provided at the product level or contractor level or both.
            * If historical sales data is provided at the product level, the data includes all products related to the search query that have been sold.
            * If historical sales data is provided at the contractor level, the data includes previous sales made with this project's contractor.

        6. **Identify Building Type**: Identify building type, including interior complexity and specialized work.

        7. **Identify Building Size**: Identify the size of the project, including number of stories, height of building, and number of total buildings in the project.

        8. **Identify Locations and Distance:** Identify the project location and distance from nearest branch. Consider if a branch is too far away from a location.
        Urban areas should have closer branches, while rural areas can have branches further away.

        9. **Identify Associated Brands:** Identify associated brands to the product. Associated brands include:
            * Armstrong Ceilings
            * Sto
            * Dryvit

        10. **Identify Available Plans:** Identify if the project has detailed and available plans and specs.

        11. **Classify Projects:**
            a. Prioritize projects based on how relevant the inputs are to the search terms.
            b. Next, prioritize projects based on the project type, as specified in the previous steps. Deprioritize non-specialized projects.
            c. Next, prioritize projects which has a high valuation of relevant materials, as specified in the previous steps. Deprioritize projects with low valuation of materials.
            d. Next, prioritize projects based on historical sales data, as specified in the previous steps. Deprioritize projects with poor historical sales for the products or with the contractor.
            e. Next, prioritize building types based on how complex the interior work is, as specified in the previous steps. Deprioritize projects with little interior work.
            f. Next, prioritize projects that have reasonable distance to the nearest branch, as specified in the previous steps. Deprioritize projects that are too far away from a branch.
            g. Next, prioritize projects that have associated brands, as specified in the previous steps. Lack of associated brands will not lower the priority.
            h. Next, increase priority if the project has detailed plans and specs. Lack of plans and specs will not lower the priority.
            i. When other factors are equal, prioritize higher-value projects (e.g., higher total dollar amount).

        12. **Estimate Relevancy:** Estimate the relevancy of each project based on the above factors and total dollar amount.

        **Input Data:**
            **Project Data:**
            {project_data}

            **Search**
            {search}

            **Boolean Filter**
            {search_terms}

            **Materials Valuation**
            {total_valuation}

            **Historical Sales Data for the last {historical_days} days:**

            {sales_data_product_location}

            {sales_data_contractor_level}

        **Example Output:**
        {{
            "Relevance": classification,
            "Reasoning": "Reasoning for classification."
        }}

        """

RELEVANCE_REASONING_PROMPT = """

      **Objective:** Generate the reasoning for a **given** ConstructConnect project relevance classification and a confidence score.

      **Instructions:**

      1.  **Analyze the provided JSON data:** Understand the project details, including relevant fields and data points. The JSON data representing the ConstructConnect project is provided in **Project Data**.

      2.  **Utilize Search Terms:** Identify mentions of relevant products, materials, and phrases within the project data. The search terms are provided in the **Search Terms** section and potentially refined in the **Search** section.

      3.  **Consider Project Types:** Identify the project type. Note if it's a specialized type with high opportunity (e.g., Hospital, University, Commercial Real Estate, Large Residential) or a lower priority type (e.g., small residential, one-time jobs).

      4.  **Identify Materials Valuation:** Identify the valuation of relevant materials provided. This is provided in the **Materials Valuation** section.

      5. **Analyze the Historical Sales Data:** If historical sales data is provided, analyze the statistics to understand past performance.
        Historical data can be provided at the product level or contractor level or both.
        * If historical sales data is provided at the product level, the data includes all products related to the search query that have been sold.
        * If historical sales data is provided at the contractor level, the data includes previous sales made with this project's contractor.

      6.  **Identify Building Type**: Identify the building type and infer the potential interior complexity and need for specialized work based on it.

      7.  **Identify Building Size**: Identify the size of the project, including number of stories, height of building, and number of total buildings in the project.

      8.  **Identify Locations and Distance:** Note the project location and its distance from the nearest branch (if provided or inferable). Consider the implications of distance (urban vs. rural context).

      8.  **Identify Associated Brands:** Check for mentions of specific associated brands like Armstrong Ceilings, Sto, Dryvit.

      9.  **Identify Available Plans:** Note if detailed plans and specifications are mentioned as being available.

      10.  **Generate Reasons:** Based on your analysis of the factors above (Steps 1-9) and the **provided Relevance Classification**, formulate a list of reasons.
            These must explain *why* the project aligns with the given classification by connecting specific project details to justify the relevance level.
            Include all relevant factors from the previous steps in your reasoning. Be concise, brief, and to the point. Prioritize the most relevant factors.
            Here is an example of a reasoning list:
            * Owned by Federal government
            * Medical Facility
            * FRP relevant material cost: $20,000
            * Plans and specs are available

      11. **Confidence Score**: Provide a confidence score between 0.0 (Low Confidence) and 1.0 (High Confidence) reflecting your certainty in the assigned **Relevance Score** and your Reasoning.
        * **Base this confidence primarily on the clarity, completeness, and consistency of the input information** used to generate reasoning in steps 1-8.
        * **Calibration Guide:**
            * **> 0.9:** Reserve for cases where **ALL critical factors** are evaluated using **explicit, complete, and unambiguous** input data.
            * **0.7 - 0.9:** Use when most factors (including critical ones) are clear, but perhaps some **secondary information** is inferred/missing, or there's **very minor ambiguity**.
            * **0.3 - 0.6:** Use when **one or more critical factors** rely partially on **inference, contain some ambiguity, or have missing details**, OR if multiple secondary factors are uncertain.
            * **< 0.3:** Use when there is **significant missing information, ambiguity, or contradiction** affecting **one or more critical factors**, making the calculated Relevance and reasoning highly speculative or uncertain.

      12. **Response Logic:** Do not include information directly from the project description. Do not include details about the search terms or matching the search term in your response. The reasoning should be limited to the most relevant aspects of the project that contribute to the relevance. The bullet points should prioritize information that is not included in the project description.

      **Example Output Format:**
      {{
          "Relevance": "Provided Relevance Classification",
          "Reasoning": [
              "Reason 1",
              "Reason 2",
              "Reason 3",
              "Reason 4"
          ],
          "Confidence": Confidence Score
      }}

      **Input Data:**
          **Project Data:**
          {project_data_json} # Ensure JSON is properly formatted string

          **Search:**
          {search}

          **Boolean Filter / Search Terms:**
          {search_terms}

          **Materials Valuation:**
          {total_valuation}

          **Historical Sales Data for the last {historical_days} days:**

            {sales_data_product_location}

            {sales_data_contractor_level}

          **Provided Relevance Classification:**
          {relevance_classification}
      """

DUPLICATE_PROJECT_PROMPT = """

        Your task is to determine if two construction projects are duplicates of each other based on the provided details.

        **Instructions:**
        1. **Carefully analyze the provided JSON data** details for Project 1 and Project 2, including features, plans, and description of work.

        2. **Analyze the project titles** to understand the context and scope of each project.

        3. **Consider the distance** between the two projects, which is provided in miles.

        4. **Consider the project owners** if that information is available.

        5. **Determine if the two projects are duplicates** or unsure based on the provided information. Use the overall context of the projects, including their titles, descriptions, and distance apart.

            * Information that would be relevant to the decision:
                - Project titles
                - Project descriptions
                - Location
            * Information that would not be relevant to the decision:
                - Project IDs
                - Dates of actions, updates, or bids
                - Bid dates or amounts

        6. **Formulate reasoning** for your decision.

        7. **Respond as a "match", "no match", or "unsure"** based on your analysis, along with your reasoning.

        **Project 1:**

        **Title:** {project_1_title}

        {project_1_owner}

        **JSON Data:**
        {project_1_json}

        **Project 2:**

        **Title:** {project_2_title}

        {project_2_owner}

        **JSON Data:**

        {project_2_json}

        **Distance:** {distance} miles

        **Example Output Format:**
        {{
            "project_match": "match" | "no_match" | "unsure",
            "Reasoning": "Your reasoning here."
        }}

        """

PRODUCT_CATEGORY_PROMPT = """

    Your task is to analyze a material item and determine which product category it belongs to.

    **Instructions:**
    1. **Analyze the Material Item** provided.
    2. **Review the Product Category List** provided. This list contains product categories you are allowed to select from.
    3. **Identify Which Product Category** the material belongs to. Consider the best fit for the material. Consider if the name of the material overlaps with the product category.
    4. **Provide Justification** for your selection, explaining why it is relevant to the product category.

    Return as a JSON object with the selected product category and your reasoning.

    **Example Output Format:**

        [{{
            "category": "CATEGORY_NAME",
            "Reasoning": "Your reasoning for selecting this category."
        }}]

    Material Item:
    {material}

    Available Product Categories:
    {product_categories}

    """

TUNING_PIPELINE_RELEVANCE_PROMPT = """

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

        4. **Note the Materials Value for the Search:** Identify the valuation relevant materials, which is provided.

        5. **Analyze the Historical Sales Data:** If historical sales data is provided, analyze the statistics to understand past performance.
            Historical data can be provided at the product level or contractor level or both.
            * If historical sales data is provided at the product level, the data includes all products related to the search query that have been sold.
            * If historical sales data is provided at the contractor level, the data includes previous sales made with this project's contractor.

        6. **Identify Building Type**: Identify building type, including interior complexity and specialized work.

        7. **Identify Locations and Distance:** Identify the project location and distance from nearest branch. Consider if a branch is too far away from a location.
        Urban areas should have closer branches, while rural areas can have branches further away.

        8. **Identify Associated Brands:** Identify associated brands to the product. Associated brands include:
            * Armstrong Ceilings
            * Sto
            * Dryvit

        9. **Identify Available Plans:** Identify if the project has detailed and available plans and specs.

        10. **Classify Projects:**
            a. Prioritize projects based on how relevant the inputs are to the search terms.
            b. Next, prioritize projects based on the project type, as specified in the previous steps. Deprioritize non-specialized projects.
            c. Next, prioritize projects which has a high valuation of relevant materials, as specified in the previous steps. Deprioritize projects with low valuation of materials.
            d. Next, prioritize projects based on historical sales data, as specified in the previous steps. Deprioritize projects with poor historical sales for the products or with the contractor.
            e. Next, prioritize building types based on how complex the interior work is, as specified in the previous steps. Deprioritize projects with little interior work.
            f. Next, prioritize projects that have reasonable distance to the nearest branch, as specified in the previous steps. Deprioritize projects that are too far away from a branch.
            g. Next, prioritize projects that have associated brands, as specified in the previous steps. Lack of associated brands will not lower the priority.
            h. Next, increase priority if the project has detailed plans and specs. Lack of plans and specs will not lower the priority.
            i. When other factors are equal, prioritize higher-value projects (e.g., higher total dollar amount).

        11. **Estimate Relevancy:** Estimate the relevancy of each project based on the above factors and total dollar amount.

        **Input Data:**

            **ProjectID:**
            {project_id}

            **Project Data:**
            {project_data}

            **Search**
            {search}

            **Boolean Filter**
            {search_terms}

            **Materials Valuation**
            {materials_valuation}

            **Historical Sales Data for the last {historical_days} days:**

            * Relevant Products: * {sales_data_product_location}

            *Sales with this Contractor: * {sales_data_contractor_level}

        **Example Output:**
        {{
            "Relevance": classification,
            "Reasoning": "Reasoning for classification."
        }}

        {examples_prompt}
        """

SEARCH_EVAL_PROMPT = """

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

CI_RELEVANCE_PROMPT_V1 = """

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

CI_RELEVANCE_PROMPT_V2 = """

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

CI_REASONING_PROMPT = """

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
          {cc_project_json}

          **Search:**
          {search}

          **Boolean Filter / Search Terms:**
          {search_terms}

          **Provided Relevance Classification:**
          {relevance_classification}
    """
