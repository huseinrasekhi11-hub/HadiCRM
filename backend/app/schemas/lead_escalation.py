from datetime import datetime

from pydantic import BaseModel
from pydantic import ConfigDict


class LeadEscalationResponse(BaseModel):
    id: int
    lead_id: int
    escalated_from_id: int
    escalated_to_id: int
    reason: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
