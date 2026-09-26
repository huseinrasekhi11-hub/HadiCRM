"""
اسکیمای ممیزی حذف لید
شامل:
  * پاسخ خنثی حذف برای کاربر حذف‌کننده (بدون هیچ اشاره‌ای به ممیزی)
  * پاسخ لیست ممیزی‌ها برای داشبورد مدیر
  * پاسخ جزئیات کامل (شامل اسنپ‌شات)
  * پاسخ احیا (Restore)
"""
from datetime import datetime

from pydantic import BaseModel
from pydantic import ConfigDict


class LeadDeleteResponse(BaseModel):
    """
    پاسخ اندپوینت حذف برای همه‌ی کاربران.
    عمداً هیچ اشاره‌ای به ممیزی/لاگ/ثبت ویژه نمی‌کند؛
    کاربر فقط یک حذف موفق معمولی می‌بیند.
    """
    status: str = "deleted"


class LeadDeletionAuditResponse(BaseModel):
    """یک ردیف در بخش «لیدهای حذف‌شده» داشبورد مدیر."""
    id: int
    lead_id: int
    customer_name: str
    mobile: str
    mobile_normalized: str | None = None
    previous_status: str
    source: str | None = None
    owner_id: int | None = None
    owner_full_name: str | None = None
    deleted_by_id: int
    deleted_by_full_name: str | None = None
    deleted_at: datetime
    sale_amount: int | None = None
    invoice_number: str | None = None
    restored_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class LeadDeletionAuditDetailResponse(LeadDeletionAuditResponse):
    """جزئیات کامل یک حذف، شامل اسنپ‌شات JSON پرونده."""
    mobile_normalized: str | None = None
    need: str | None = None
    loss_reason: str | None = None
    sold_products: str | None = None
    created_by_id: int | None = None
    restored_by_id: int | None = None
    snapshot: dict = {}

    model_config = ConfigDict(from_attributes=True)


class LeadRestoreResponse(BaseModel):
    status: str = "restored"
    lead_id: int
    restored_at: datetime
