"""
# Example usage:
from utils import get_secret
from config import get_settings
from enum import Enum

from pydantic import BaseModel

class Category(Enum):
    ELECTRONICS = "electronics"
    CLOTHING = "clothing"
    BOOKS = "books"

class Product(BaseModel):
    name: str
    category: Category
    price: float

api_key = get_secret(secret_name=settings.GEMINI_API_KEY_SECRET_NAME)
config = GeminiClientConfig(
    api_key=api_key, model="gemini-2.0-flash", temperature=0.7, candidate_count=1
)

client = GeminiClient(config=config)

# Generate single enum value
category = client.generate_structured(
    "What category would a laptop belong to?", Category, mime_type="text/x.enum"
)
print(f"Category: {category}")

# Generate list of products
products = client.generate_json_list(
    "List 3 products with their categories and prices", Product
)
print("\nProducts:")
for product in products:
    print(f"- {product.name} ({product.category}): ${product.price:.2f}")
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Type, TypeVar

from google import genai
from pydantic import BaseModel
from google.genai import types
from google.genai.types import(
    GenerateContentConfig,
    SafetySetting,
)

T = TypeVar("T")


class MockStructuredResponse:
    """Mock class for structured response"""

    def __init__(self, text: str):
        self.text = text

    def model_dump_json(self):
        return self.text


@dataclass
class GeminiClientConfig:
    """Configuration for GeminiClient"""

    model: str
    model_type: str
    project_id: str 
    location: str
    temperature: float = 0
    candidate_count: int = 1
    max_output_tokens: int = 4096
    seed: int = 42


class GeminiClient:
    """Client for generating structured outputs using Gemini API"""

    def __init__(self, config: GeminiClientConfig):
        """Initialize the Gemini client with optional configuration"""
        self.config = config
        self.client = genai.Client(vertexai=True, project=config.project_id, location=config.location)

    def generate_structured(
        self, prompt: str, response_type: Type[T], mime_type: str = "application/json"
    ) -> T:
        """
        Generate structured output based on provided response type

        Args:
            prompt: The input prompt for generation
            response_type: The expected response type (Pydantic model or enum)
            mime_type: Response MIME type ('application/json' or 'text/x.enum')

        Returns:
            Instance of response_type containing the structured response
        """
        try:

            safety_settings = [
                SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                    threshold=types.HarmBlockThreshold.BLOCK_NONE,
                ), 
                SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                    threshold=types.HarmBlockThreshold.BLOCK_NONE,
                ),
                SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                    threshold=types.HarmBlockThreshold.BLOCK_NONE,
                ),
                SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                    threshold=types.HarmBlockThreshold.BLOCK_NONE,
                ),
            ]
            
            # Configuration for tuned model without response type 
            config_tuned = GenerateContentConfig(
                temperature=self.config.temperature,
                candidate_count=self.config.candidate_count,
                max_output_tokens=self.config.max_output_tokens,
                seed=self.config.seed,
                safety_settings=safety_settings,
            )

            # Configuration for standard model with response type 
            config = GenerateContentConfig(
                temperature=self.config.temperature,
                candidate_count=self.config.candidate_count,
                max_output_tokens=self.config.max_output_tokens,
                response_mime_type=mime_type,
                response_schema=response_type,
                seed=self.config.seed,
                safety_settings=safety_settings,
            )

            if self.config.model_type == "tuned":

                # Generate content for tuned model
                response = self.client.models.generate_content(
                    model=self.config.model,
                    contents=prompt, 
                    config=config_tuned
                )
                
                return MockStructuredResponse(text=response.text)
                
            else:

                # Generate content for standard model
                response = self.client.models.generate_content(
                    model=self.config.model,
                    contents=prompt,
                    config=config,
                )

                if issubclass(response_type, Enum):
                    return response_type(response.text.strip())
                else:
                    return response.parsed

        except Exception as e:
            raise Exception(f"Error generating structured output: {str(e)}")

    def generate_json_list(self, prompt: str, item_type: Type[BaseModel]) -> list[Any]:
        """
        Generate a list of structured items

        Args:
            prompt: The input prompt for generation
            item_type: Pydantic model type for list items

        Returns:
            List of structured items
        """
        return self.generate_structured(prompt, list[item_type])
