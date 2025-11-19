import sys
from pathlib import Path

CLOUD_FUNCTION_DIR = Path(__file__).resolve().parents[1] / "CloudFunction"
if str(CLOUD_FUNCTION_DIR) not in sys.path:
    sys.path.insert(0, str(CLOUD_FUNCTION_DIR))

from utils.prompts import TUNING_PIPELINE_RELEVANCE_PROMPT

RELEVANCE_PROMPT = TUNING_PIPELINE_RELEVANCE_PROMPT
