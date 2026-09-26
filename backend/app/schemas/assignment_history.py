from datetime import datetime

from pydantic import BaseModel
from pydantic import ConfigDict


class AssignmentHistoryResponse(BaseModel):
    id: int
    lead_id: int
    assigned_by_id: int
    assigned_to_id: int
    note: str | None
    assigned_at: datetime

    model_config = ConfigDict(from_attributes=True)
