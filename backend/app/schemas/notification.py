from datetime import datetime

from pydantic import BaseModel
from pydantic import ConfigDict


class NotificationResponse(BaseModel):
    id: int
    lead_id: int | None
    notification_type: str
    title: str
    message: str
    is_read: bool
    created_at: datetime

    # برای نمایش دکمه‌ی «تماس» مستقیم از داخل نوتیفیکیشن، بدون درخواست اضافه
    lead_customer_name: str | None = None
    lead_mobile: str | None = None

    model_config = ConfigDict(from_attributes=True)


class NotificationSummary(BaseModel):
    unread_count: int
