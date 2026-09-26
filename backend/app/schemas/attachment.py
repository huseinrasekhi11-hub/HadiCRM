from pydantic import BaseModel, ConfigDict
from datetime import datetime

class AttachmentResponse(BaseModel):
    id: int
    file_name: str
    file_path: str
    uploaded_by_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
