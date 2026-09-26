"""
اسکیمای تایم‌لاین یکپارچه‌ی مدیریتی
پاسخ یکپارچه برای نمایش «کل چرخه‌ی حیات پرونده» در پنل مدیریت.
"""
from datetime import datetime

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field


class AdminTimelineEvent(BaseModel):
    """
    یک رویداد واحد در تاریخچه‌ی کامل پرونده.

    منبع رویداد (source):
      activity       → جدول فعالیت‌ها
      assignment     → تاریخچه‌ی ارجاع (بدون اکتیویتی متناظر)
      escalation     → ارجاع اضطراری (بدون اکتیویتی متناظر)
      attachment     → فایل ضمیمه
      deletion_audit → ممیزی حذف/احیا (بدون اکتیویتی متناظر)

    نوع رویداد (event_type) نمونه‌ها:
      lead_created / status_change / lead_assigned / escalated /
      task_created / task_completed / followup_set /
      duplicate_detected / attachment_uploaded /
      lead_deleted / lead_restored / note / call / ...
    """
    event_id: str
    source: str
    event_type: str
    title: str
    description: str | None = None
    actor_id: int | None = None
    actor_name: str | None = None
    occurred_at: datetime | None = None
    metadata: dict = Field(default_factory=dict)


class AdminLeadTimelineResponse(BaseModel):
    """
    پاسخ کامل اندپوینت تاریخچه‌ی مدیریتی:
    مشخصات فعلی پرونده + جریان کامل رویدادها.
    برای پرونده‌های حذف‌شده نیز مقداردهی می‌شود.
    """
    lead_id: int
    customer_name: str
    mobile: str
    status: str
    is_deleted: bool
    deleted_at: datetime | None = None
    owner_id: int
    owner_full_name: str | None = None
    created_at: datetime
    duplicate_count: int = 0
    events: list[AdminTimelineEvent] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
