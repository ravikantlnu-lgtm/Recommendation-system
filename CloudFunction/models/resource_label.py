from pydantic import BaseModel

class ResourceLabel(BaseModel):
    key: str
    value: str
