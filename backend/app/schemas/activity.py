from datetime import datetime

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import model_validator

# انواع قبلی حفظ شده‌اند (سازگاری با داده‌های موجود)؛ انواع جدید طبق
# فرآیند کسب‌وکار (مرحله‌ی «ثبت جزئیات و چرخه‌ی پیگیری») اضافه شده‌اند.
ACTIVITY_TYPES = {
    "note",
    "call",
    "meeting",
    "message",
    "status_change",
    "lead_created",
    "lead_assigned",
    "task_created",
    "task_completed",
    # --- انواع جدید اقدام (Action) ---
    "callback",               # تماس مجدد
    "proforma_sent",          # ارسال پیش‌فاکتور
    "catalog_sent",           # ارسال کاتالوگ
    "technician_dispatched",  # اعزام کارشناس
    "whatsapp",               # واتساپ
    "sms",                    # پیامک
    "email",                  # ایمیل
    "escalated",              # ارجاع خودکار به مدیر (قانون ۳)
    "followup_set",           # تنظیم دستی زمان پیگیری
    "duplicate_detected",     # ثبت تکراری شناسایی و به این پرونده متصل شد
    "lead_deleted",           # پرونده حذف شد (رویداد سیستمی/ممیزی)
    "lead_restored",          # پرونده حذف‌شده احیا شد (توسط مدیر)
    "sale_item_added",        # ثبت/بروزرسانی اقلام فروش ریالی
    "other",                  # سایر
}

# اقدام‌های «انسانی» که کارشناس هنگام ثبتشان باید پیگیری بعدی را مشخص کند.
# انواع سیستمی (تغییر وضعیت، ارجاع، ایجاد/اتمام وظیفه، کشف تکراری،
# حذف، احیا و اقلام فروش) از این قاعده مستثنی هستند چون توسط خود سیستم
# و نه با فرم اقدام کارشناس ثبت می‌شوند.
ACTION_TYPES_REQUIRING_FOLLOWUP = {
    "note",
    "call",
    "callback",
    "meeting",
    "message",
    "proforma_sent",
    "catalog_sent",
    "technician_dispatched",
    "whatsapp",
    "sms",
    "email",
    "other",
}


class ActivityCreate(BaseModel):
    activity_type: str = Field(
        pattern="|".join(f"^{activity_type}$" for activity_type in ACTIVITY_TYPES)
    )
    title: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)

    # نتیجه‌ی اقدام (اختیاری، مثلاً: پاسخ نداد / علاقه‌مند / شماره اشتباه)
    outcome: str | None = Field(default=None, max_length=50)

    # پیگیری اجباری بعدی: یا next_follow_up یا no_followup_reason باید پر شود
    next_follow_up: datetime | None = None
    no_followup_reason: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def validate_mandatory_followup(self):
        """
        طبق فرآیند کسب‌وکار: هر بار که یک اقدام انسانی ثبت می‌شود، باید
        زمان پیگیری بعدی مشخص شود؛ در غیر این صورت دلیل «بدون پیگیری»
        الزامی است. این قانون فقط برای اقدام‌های انسانی اعمال می‌شود؛
        رویدادهای سیستمی (تغییر وضعیت، ارجاع و...) از این قانون معاف‌اند.
        """
        if self.activity_type in ACTION_TYPES_REQUIRING_FOLLOWUP:
            if self.next_follow_up is None and not (self.no_followup_reason or "").strip():
                raise ValueError(
                    "پیگیری بعدی مشخص نشده است. باید next_follow_up را انتخاب کنید "
                    "یا در صورت انتخاب «بدون پیگیری»، دلیل آن را وارد کنید."
                )
        return self


class ActivityResponse(BaseModel):
    id: int
    lead_id: int
    user_id: int
    activity_type: str
    title: str
    description: str | None
    outcome: str | None = None
    next_follow_up: datetime | None = None
    no_followup_reason: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
