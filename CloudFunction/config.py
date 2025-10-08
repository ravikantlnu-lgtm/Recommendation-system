import os
import shutil
from functools import lru_cache
from typing import ClassVar

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# from dotenv import load_dotenv


version = os.getenv("VERSION", "deployed")

ENV = os.getenv("ENV")

if ENV == "dev":
    shutil.copy(".env.DEV", ".env")
elif ENV == "prod":
    shutil.copy(".env.PROD", ".env")


class Settings(BaseSettings):
    PROJECT_ID: str = Field(..., env="PROJECT_ID")
    PROJECT_NUMBER: str = Field(..., env="PROJECT_NUMBER")
    LOCATION: str = Field(..., env="LOCATION")
    REGION: str = Field(..., env="REGION")
    TUNED_MODEL_REGION: str = Field(..., env="TUNED_MODEL_REGION")

    # BigQuery details
    BIGQUERY_DATASET: str = Field(..., env="BIGQUERY_DATASET")
    CC_FEED_TABLE_ID: str = Field(..., env="CC_FEED_TABLE_ID")
    DODGE_FEED_TABLE_ID: str = Field(..., env="DODGE_FEED_TABLE_ID")
    SEARCHES_TABLE_ID: str = Field(..., env="SEARCHES_TABLE_ID")
    SEARCHES_STAGING_TABLE_ID: str = Field(..., env="SEARCHES_STAGING_TABLE_ID")
    SEARCH_TERRITORY_TABLE_ID: str = Field(..., env="SEARCH_TERRITORY_TABLE_ID")
    SEARCH_TERRITORY_STAGING_TABLE_ID: str = Field(
        ..., env="SEARCH_TERRITORY_STAGING_TABLE_ID"
    )
    RANKING_COLUMNS_TABLE_ID: str = Field(..., env="RANKING_COLUMNS_TABLE_ID")
    RELEVANT_MATERIALS_TABLE_ID: str = Field(..., env="RELEVANT_MATERIALS_TABLE_ID")
    ASSIGNED_SEARCH_TABLE_ID: str = Field(..., env="ASSIGNED_SEARCH_TABLE_ID")
    RELEVANT_CATEGORIES_TABLE_ID: str = Field(..., env="RELEVANT_CATEGORIES_TABLE_ID")
    PROJECT_RELEVANCE_TABLE_ID: str = Field(..., env="PROJECT_RELEVANCE_TABLE_ID")
    WORKFLOW_FAILURE_EVENTS_TABLE_ID: str = Field(
        ..., env="WORKFLOW_FAILURE_EVENTS_TABLE_ID"
    )
    TERRITORIES_TABLE_ID: str = Field(..., env="TERRITORIES_TABLE_ID")
    TERRITORIES_STAGING_TABLE_ID: str = Field(..., env="TERRITORIES_STAGING_TABLE_ID")
    ASSIGNED_SEARCH_TABLE_ID: str = Field(..., env="ASSIGNED_SEARCH_TABLE_ID")
    HIST_DATALOAD_TABLE_ID: str = Field(..., env="HIST_DATALOAD_TABLE_ID")
    DODGE_FEED_TABLE_ID: str = Field(..., env="DODGE_FEED_TABLE_ID")
    PROJECTS_FOR_DEDUPLICATION_TABLE_ID: str = Field(
        ..., env="PROJECTS_FOR_DEDUPLICATION_TABLE_ID"
    )
    LLM_DEDUPLICATION_RESULT_TABLE_ID: str = Field(
        ..., env="LLM_DEDUPLICATION_RESULT_TABLE_ID"
    )
    PRIMARY_PROJECT_LEAD_TABLE_ID: str = Field(..., env="PRIMARY_PROJECT_LEAD_TABLE_ID")
    SOURCE_LINKING_TABLE_ID: str = Field(..., env="SOURCE_LINKING_TABLE_ID")
    PRODUCT_CATEGORY_MATERIALS_MAP_TABLE_ID: str = Field(
        ..., env="PRODUCT_CATEGORY_MATERIALS_MAP_TABLE_ID"
    )
    SEARCH_PRODUCT_CATEGORY_MAP_TABLE_ID: str = Field(
        ..., env="SEARCH_PRODUCT_CATEGORY_MAP_TABLE_ID"
    )
    CONSOLIDATED_PRIMARY_PROJECT_LEAD_TABLE_ID: str = Field(..., env="CONSOLIDATED_PRIMARY_PROJECT_LEAD_TABLE_ID")
    COALESCED_PRIMARY_PROJECT_TABLE_ID: str = Field(..., env="COALESCED_PRIMARY_PROJECT_TABLE_ID")

    SALES_PROJECT_ID: str = Field(..., env="SALES_PROJECT_ID")
    BIGQUERY_SALES_DATASET: str = Field(..., env="BIGQUERY_SALES_DATASET")
    GENAI_TABLE: str = Field(..., env="GENAI_TABLE")
    SALES_PRODUCTS_TABLE: str = Field(..., env="SALES_PRODUCTS_TABLE")
    SALES_CUSTOMER_TABLE: str = Field(..., env="SALES_CUSTOMER_TABLE")

    # Vertex AI details
    BASE_LLM_MODEL: str = Field(..., env="BASE_LLM_MODEL")
    LATEST_TUNED_LLM_ENDPOINT_PROJECT_TO_SEARCH: str = Field(
        ..., env="LATEST_TUNED_LLM_ENDPOINT_PROJECT_TO_SEARCH"
    )
    LATEST_TUNED_LLM_ENDPOINT_ASSIGN_RELEVANCE: str = Field(
        ..., env="LATEST_TUNED_LLM_ENDPOINT_ASSIGN_RELEVANCE"
    )
    LLM_ENDPOINT_REASONING: str = Field(..., env="LLM_ENDPOINT_REASONING")

    # Cloud storage
    GCS_BUCKET: str = Field(..., env="GCS_BUCKET")
    GCS_SOURCE_BUCKET: str = Field(..., env="GCS_SOURCE_BUCKET")
    DODGE_GCS_SOURCE_BUCKET: str = Field(..., env="DODGE_GCS_SOURCE_BUCKET")

    # Workflow
    WORKFLOW_INVOCATION_NAME: str = Field(..., env="WORKFLOW_INVOCATION_NAME")
    WORKFLOW_DEDUPLICATION_RESOLUTION_NAME: str = Field(
        ..., env="WORKFLOW_DEDUPLICATION_RESOLUTION_NAME"
    )
    WORKFLOW_INVOCATION_LOCATION: str = Field(..., env="WORKFLOW_INVOCATION_LOCATION")
    WORKFLOW_INVOCATION_SA: str = Field(..., env="WORKFLOW_INVOCATION_SA")

    CLOUD_TASK_LOCATION: str = Field(..., env="CLOUD_TASK_LOCATION")
    CLOUD_TASK_SEND_PROJECT_TO_QUEUE_QUEUE: str = Field(
        ..., env="CLOUD_TASK_SEND_PROJECT_TO_QUEUE_QUEUE"
    )
    CLOUD_TASK_ASSIGN_SEARCH_QUEUE: str = Field(
        ..., env="CLOUD_TASK_ASSIGN_SEARCH_QUEUE"
    )
    CLOUD_TASK_REROUTE_TO_SEARCH_OR_RELEVANCE_QUEUE: str = Field(
        ..., env="CLOUD_TASK_REROUTE_TO_SEARCH_OR_RELEVANCE_QUEUE"
    )

    # CLoud Functions
    DATA_INTAKE_CLOUD_FUNCTION_URL: str = Field(
        ..., env="DATA_INTAKE_CLOUD_FUNCTION_URL"
    )
    HIST_XML_LOAD_CLOUD_FUNCTION_URL: str = Field(
        ..., env="HIST_XML_LOAD_CLOUD_FUNCTION_URL"
    )
    BATCH_UPSERT_LEADS_CLOUD_FUNCTION_URL: str = Field(
        ..., env="BATCH_UPSERT_LEADS_CLOUD_FUNCTION_URL"
    )
    TRIGGER_BATCH_UPSERT_CLOUD_FUNCTION_URL: str = Field(
        ..., env="TRIGGER_BATCH_UPSERT_CLOUD_FUNCTION_URL"
    )
    WORKFLOW_FAILURE_CLOUD_FUNCTION_URL: str = Field(
        ..., env="WORKFLOW_FAILURE_CLOUD_FUNCTION_URL"
    )
    SEARCH_TERRITORY_UPDATES_CLOUD_FUNCTION_URL: str = Field(
        ..., env="SEARCH_TERRITORY_UPDATES_CLOUD_FUNCTION_URL"
    )
    BACKFILL_PROJECTS_CLOUD_FUNCTION_URL: str = Field(
        ..., env="BACKFILL_PROJECTS_CLOUD_FUNCTION_URL"
    )
    DEDUPLICATE_PROJECTS_BATCH_CLOUD_FUNCTION_URL: str = Field(
        ..., env="DEDUPLICATE_PROJECTS_BATCH_CLOUD_FUNCTION_URL"
    )
    UNIFICATION_CLOUD_FUNCTION_URL: str = Field(
        ..., env="UNIFICATION_CLOUD_FUNCTION_URL"
    )

    # GenAI
    GEMINI_API_KEY_SECRET_NAME: str = Field(..., env="GEMINI_API_KEY_SECRET_NAME")

    # Matching Parameters
    RADIUS_MILES: int = Field(..., env="RADIUS_MILES")
    MAX_BRANCHES: int = Field(..., env="MAX_BRANCHES")

    # Dynamics
    DM_INSTANCE_URL: str = Field(..., env="DM_INSTANCE_URL")
    DM_TERRITORY_TABLE_ID: str = Field(..., env="DM_TERRITORY_TABLE_ID")
    DM_SEARCH_TERRITORY_MAP_ID: str = Field(..., env="DM_SEARCH_TERRITORY_MAP_ID")
    DM_SEARCH_TABLE_ID: str = Field(..., env="DM_SEARCH_TABLE_ID")
    DM_SALES_PROFILE_ID: str = Field(..., env="DM_SALES_PROFILE_ID")
    DM_LEAD_ID: str = Field(..., env="DM_LEAD_ID")
    DM_USER_ID: str = Field(..., env="DM_USER_ID")
    DM_SALES_BRANCH_ID: str = Field(..., env="DM_SALES_BRANCH_ID")
    DM_BRANCH_OPPORTUNITY_ID: str = Field(..., env="DM_BRANCH_OPPORTUNITY_ID")
    DM_SALESBRANCHSET: str = Field(..., env="DM_SALESBRANCHSET")
    DM_USERSALESPROFILESET: str = Field(..., env="DM_USERSALESPROFILESET")

    DM_DEFAULT_SALES_REP_ID: str = Field(..., env="DM_DEFAULT_SALES_REP_ID")
    DM_PROFILE_CATEGORIES_ID: str = Field(..., env="DM_PROFILE_CATEGORIES_ID")
    DM_PRODUCT_CATEGORIES_ID: str = Field(..., env="DM_PRODUCT_CATEGORIES_ID")
    DM_EXTERNALLEAD_ID: str = Field(..., env="DM_EXTERNALLEAD_ID")

    # Matching Parameters
    RADIUS_MILES: int = Field(..., env="RADIUS_MILES")
    MAX_BRANCHES: int = Field(..., env="MAX_BRANCHES")

    # Firestore variables
    FIRESTORE_DATABASE: str = Field(..., env="FIRESTORE_DATABASE")
    FIRESTORE_COLLECTION: str = Field(..., env="FIRESTORE_COLLECTION")

    # Concurrency variables
    MAX_WORKERS: int = Field(..., env="MAX_WORKERS")

    # Confidence threshold
    CONFIDENCE_THRESHOLD: float = Field(..., env="CONFIDENCE_THRESHOLD")

    # Historical data variables
    HISTORICAL_SALES_DAYS: int = Field(..., env="HISTORICAL_SALES_DAYS")

    # Dynamically choose the environment file
    model_config = SettingsConfigDict(
        env_file=".env.DEV" if version == "local" else ".env"
    )


@lru_cache
def get_settings():
    return Settings()


# settings = get_settings()

# print(f"PROJECT_ID: {settings.PROJECT_ID}")
# print(f"PROJECT_NO: {settings.PROJECT_NUMBER}")
# print(f"BQ_DATASET: {settings.BIGQUERY_DATASET}") # print(f"PROJECT_NO: {settings.PROJECT_NUMBER}")
# print(f"BQ_DATASET: {settings.BIGQUERY_DATASET}")
