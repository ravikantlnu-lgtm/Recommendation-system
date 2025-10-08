RELEVANCE_PROMPT = """ 

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
