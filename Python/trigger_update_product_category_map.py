import os
import sys
import re
import pandas as pd
import pandas_gbq
from enum import Enum
from pydantic import BaseModel
from typing import Type, List

#  Add CloudFunction directory path (adjust if necessary)
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cloud_function_path = os.path.join(project_root, "CloudFunction")
if cloud_function_path not in sys.path:
    sys.path.insert(0, cloud_function_path)

os.chdir(cloud_function_path)

try:
    from config import get_settings
    from services import BigQueryManager, GeminiClient, GeminiClientConfig
    from utils.common import get_secret, fetch_latest_model_endpoint
    from utils.prompts import PRODUCT_CATEGORY_PROMPT
except ImportError as e:
    print(f"Error importing shared modules: {e}")
    print(
        "Please ensure the CloudFunction directory is structured correctly and accessible."
    )
    raise

settings = get_settings()


# Function to clean material names for enum creation
def sanitize_enum_name(name: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    if not name or not name[0].isalpha():
        name = "PRODUCT_CATEGORY_" + name
    return name.upper()


# Function to dynamically create an Enum class and Pydantic BaseModel for categories
def create_llm_response_type(product_categories: list[str]) -> Type[Enum]:
    # category enum
    product_categories = {sanitize_enum_name(category): category for category in product_categories}
    DynamicsProductCategoryEnum = Enum("DYNAMICS_PRODUCT_CATEGORY_ENUM", product_categories)

    # Pydantic BaseModel for LLM response
    class CategoryRelevanceResult(BaseModel):
        category: DynamicsProductCategoryEnum
        Reasoning: str

    return CategoryRelevanceResult


def llm_generate_product_category_for_material(
    material: str, product_categories: List[str], response_type: Type[BaseModel]
) -> BaseModel:
    # Construct prompt
    prompt = PRODUCT_CATEGORY_PROMPT.format(
        material=material,
        product_categories=product_categories,
    )

    gemini_api_key = get_secret(
        project_number=settings.PROJECT_NUMBER,
        secret_name=settings.GEMINI_API_KEY_SECRET_NAME,
    )

    model, is_tuned_model = fetch_latest_model_endpoint(llm_prompt_type="base_llm")

    if is_tuned_model:
        model_type = "tuned"
    else:
        model_type = "base"

    # Initialize client and configuration
    config = GeminiClientConfig(
        model=model, 
        model_type=model_type,
        project_id=settings.PROJECT_ID,
        location=settings.REGION
    )
    gemini_client = GeminiClient(config=config)

    # Generate JSON list using the Gemini client
    return gemini_client.generate_structured(
        prompt=prompt,
        response_type=response_type,
    )


def main():
    # Initialize BigQuery Client
    try:
        big_query_client = BigQueryManager(dataset_id=settings.BIGQUERY_DATASET)
    except Exception as e:
        print(f"FATAL: Failed to initialize BigQuery Client. Exiting. Error: {e}")
        
        return

    # Fetch product categories from BigQuery 
    print("Fetching product categories from BigQuery...")
    product_categories_query = f"""select PRODUCT_PRIMARY_CAT_CODE, PRODUCT_PRIMARY_CAT_DESC from 
        `{settings.SALES_PROJECT_ID}.{settings.BIGQUERY_SALES_DATASET}.{settings.SALES_PRODUCTS_TABLE}`
        where PRODUCT_PRIMARY_CAT_CODE is not null and PRODUCT_PRIMARY_CAT_CODE != ''
        and PRODUCT_PRIMARY_CAT_DESC is not null and PRODUCT_PRIMARY_CAT_DESC != ''
        """
    product_categories_df = big_query_client.query_table(product_categories_query, to_dataframe=True)

    # Clean product categories
    product_categories_df['PRODUCT_PRIMARY_CAT_DESC'] = product_categories_df['PRODUCT_PRIMARY_CAT_DESC'].str.strip().str.lower()    
    product_categories_df = product_categories_df.dropna()
    product_categories_df = product_categories_df.drop_duplicates() 

    # Remove non-product categories
    non_product_categories = ['other', 'customer rebates', 'delivery charges', 'mi high temp', 'mi other', 
                                'non inventory', 'building rent', '7299', 'expense', 'xexpense']
    product_categories_df = product_categories_df[~(product_categories_df['PRODUCT_PRIMARY_CAT_DESC'].fillna('')).isin(non_product_categories)]
    product_categories = product_categories_df['PRODUCT_PRIMARY_CAT_DESC'].unique().tolist()
    
    # Fetch relevant materials from BigQuery
    print("Fetching materials from BigQuery...")
    materials_query = f"""select division, material, code from 
        `{settings.PROJECT_ID}.{settings.BIGQUERY_DATASET}.{settings.RELEVANT_MATERIALS_TABLE_ID}`
        where division is not null"""

    materials_df = big_query_client.query_table(materials_query, to_dataframe=True)

    # Create dynamic Pydantic model for LLM
    print("Creating response type for LLM...")
    CategoryRelevanceResult = create_llm_response_type(product_categories)

    # Initialize an empty DataFrame to store results
    product_category_map_table = pd.DataFrame(columns=['fbm_productcatcode', 'product_category_name', 'division', 'material', 'code'])

    for _, row in materials_df.iterrows(): 

        material = row['material']
        material_division = row['division']
        material_code = row['code']
        response = llm_generate_product_category_for_material(material, product_categories, CategoryRelevanceResult)
        print(response)
        if not response:
            print(f"No product category found for material: {material}")
            continue

        product_category_name = response.category.value 
        product_category_code = product_categories_df[product_categories_df['PRODUCT_PRIMARY_CAT_DESC'] == product_category_name]['PRODUCT_PRIMARY_CAT_CODE'].values[0]
        
        response_df = pd.DataFrame([{
            'fbm_productcatcode': product_category_code,
            'product_category_name': product_category_name,
            'division': material_division,
            'material': material,
            'code': material_code,
        }])

        product_category_map_table = pd.concat([product_category_map_table, response_df], ignore_index=True)

    print("Results collected. Preparing to write to BigQuery...")
    print(product_category_map_table)
    if not product_category_map_table.empty:

        product_category_map_table['fbm_productcatcode'] = product_category_map_table['fbm_productcatcode'].astype(str)
        product_category_map_table = product_category_map_table[['fbm_productcatcode', 'product_category_name', 'division', 'material', 'code']]

        # Write results to BigQuery product category-materials mapping table
        try:
            pandas_gbq.to_gbq(
                product_category_map_table,
                destination_table=f"{settings.BIGQUERY_DATASET}.{settings.PRODUCT_CATEGORY_MATERIALS_MAP_TABLE_ID}",
                project_id=settings.PROJECT_ID,
                if_exists="replace",
            )
            print("Materials search results successfully written to BigQuery.")
        except Exception as e:
            print(f"Error writing to BigQuery: {e}")


if __name__ == "__main__":
    main()
