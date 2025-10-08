from typing import List, Optional

from models.resource_label import ResourceLabel
from pydantic import BaseModel


class DefaultLog(BaseModel):
    log_timestamp: str
    resource_type: Optional[str] = None
    resource_labels: List[ResourceLabel] = []
    log_name: Optional[str] = None
    log_message: str
    json_payload: Optional[str] = None
