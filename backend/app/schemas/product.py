"""اسکیمای محصولات (کاتالوگ کالا)"""
from datetime import datetime

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field


class ProductCreate(BaseModel):
    name: str = Field(max_length=100)


class ProductResponse(BaseModel):
    id: int
    name: str
    is_active: bool = True
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
