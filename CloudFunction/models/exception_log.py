from typing import List, Optional

from models.resource_label import ResourceLabel
from pydantic import BaseModel


class ExceptionLog(BaseModel):
    log_timestamp: str
    severity: str = "ERROR"  
    resource_type: Optional[str] = None
    resource_labels: List[ResourceLabel] = []
    log_name: Optional[str] = None
    log_message: str
    exception_type: Optional[str] = None
    stack_trace: Optional[str] = None
    json_payload: Optional[str] = None