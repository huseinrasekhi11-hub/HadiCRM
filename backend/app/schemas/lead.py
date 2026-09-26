from datetime import datetime
from datetime import timezone
from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator
from pydantic import model_validator

import re

from app.core.text_normalization import normalize_mobile
from app.schemas.sale_item import SaleItemInput

# Iranian mobile canonical form after normalization: 09xxxxxxxxx
_MOBILE_CANONICAL_RE = re.compile(r"^09\d{9}$")


def _validate_mobile(value: str) -> str:
    """Reject blank/garbage mobiles at the schema boundary.

    Previously any string (e.g. 'abc', '   ') was accepted on CREATE,
    producing leads without a duplicate-detection key; values longer
    than the DB column (VARCHAR(20)) even crashed with HTTP 500.
    """
    canonical = normalize_mobile(value)
    if not canonical or not _MOBILE_CANONICAL_RE.match(canonical):
        raise ValueError(
            "شماره موبایل معتبر نیست. نمونه‌ی قابل قبول: 09121234567"
        )
    return value.strip()

# پابرجا مانده: مراحل دقیق قیف فروش (پایپ‌لاین داخلی شرکت).
# تغییر تجویزشده: وضعیت «فروش موفق» از این پس با مقدار رسمی
# «final_factor» شناخته می‌شود؛ زیرا صدور فاکتور/عامل نهایی به معنای
# تبدیل موفق لید است. مقدار قبلی (closed_won) فقط به‌عنوان نام مستعار
# منسوخ‌شده برای سازگاری دوره‌ی گذار پذیرفته و نرمال می‌شود.
LEAD_STATUSES = {
    "new",
    "contacted",
    "no_answer",
    "negotiating",
    "waiting_customer",
    "catalog_sent",
    "price_sent",
    "proforma",
    "invoice",
    "final_factor",
    "closed_lost",
}

CLOSED_STATUSES = {"final_factor", "closed_lost"}

# وضعیت موفق رسمی (کاننیکال) — تنها نقطه‌ی تعریف در کل بک‌اند
FINAL_FACTOR_STATUS = "final_factor"

# وضعیت عدم فروش رسمی
CLOSED_LOST_STATUS = "closed_lost"

# ترتیب رسمی مراحل قیف برای پاسخ‌های پایپ‌لاین (صفرگذاری‌شده و مرتب)
PIPELINE_ORDER = [
    "new",
    "contacted",
    "no_answer",
    "negotiating",
    "waiting_customer",
    "catalog_sent",
    "price_sent",
    "proforma",
    "invoice",
    FINAL_FACTOR_STATUS,
    CLOSED_LOST_STATUS,
]

# نام‌های مستعار منسوخ‌شده؛ صرفاً برای سازگاری با کلاینت‌های قدیمی.
# هر ورودی با این مقادیر به‌صورت خودکار به مقدار رسمی تبدیل می‌شود.
DEPRECATED_STATUS_ALIASES = {
    "closed_won": FINAL_FACTOR_STATUS,
    # واژگان ربات بله → واژگان رسمی وب (رفع ناسازگاری دو زبانِ وضعیت)
    "won": FINAL_FACTOR_STATUS,
    "lost": CLOSED_LOST_STATUS,
    "followup": "contacted",
    "noanswer": "no_answer",
    "survey": "waiting_customer",
    "service": "waiting_customer",
}


def canonical_status(status: str | None) -> str | None:
    """تبدیل نام‌های مستعار قدیمی به وضعیت رسمی فعلی."""
    if status is None:
        return None
    return DEPRECATED_STATUS_ALIASES.get(status, status)


# دلایل «عدم فروش» طبق سند کسب‌وکار؛ برای گزارش‌گیری تحلیلی استفاده می‌شوند.
LOSS_REASONS = {
    "price",           # قیمت
    "competitor",      # رقیب
    "no_budget",       # عدم بودجه
    "no_need",         # عدم نیاز
    "no_response",     # عدم پاسخ‌گویی مشتری
    "wrong_customer",  # مشتری اشتباه
    "other",           # سایر
}


class LeadCreate(BaseModel):
    customer_name: str = Field(min_length=1, max_length=100)
    mobile: str = Field(min_length=1, max_length=20)
    source: str = Field(min_length=1, max_length=50)
    need: str | None = Field(default=None, max_length=500)
    # اختیاری: یادداشت همراه ثبت؛ فقط هنگام «ثبت تکراری» در تاریخچه ذخیره می‌شود
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("customer_name")
    @classmethod
    def check_customer_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("نام مشتری نمی‌تواند خالی باشد.")
        return v.strip()

    @field_validator("mobile")
    @classmethod
    def check_mobile(cls, v: str) -> str:
        return _validate_mobile(v)

    @field_validator("source")
    @classmethod
    def check_source(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("منبع_lead نمی‌تواند خالی باشد.")
        return v.strip()


class LeadUpdate(BaseModel):
    """
    ویرایش اطلاعات هویتی پرونده.
    حداقل یک فیلد الزامی است؛ تغییر موبایل با نرمال‌سازی مجدد و
    بررسی تداخل با سایر پرونده‌ها همراه است.
    """
    customer_name: str | None = Field(default=None, max_length=100)
    mobile: str | None = Field(default=None, max_length=20)
    source: str | None = Field(default=None, max_length=50)
    need: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_update_payload(self):
        values = (self.customer_name, self.mobile, self.source, self.need)
        if all(value is None for value in values):
            raise ValueError("حداقل یک فیلد برای ویرایش الزامی است.")
        if self.customer_name is not None and not self.customer_name.strip():
            raise ValueError("نام مشتری نمی‌تواند خالی باشد.")
        return self


class LeadStatusUpdate(BaseModel):
    status: Literal[
        "new",
        "contacted",
        "no_answer",
        "negotiating",
        "waiting_customer",
        "catalog_sent",
        "price_sent",
        "proforma",
        "invoice",
        "final_factor",
        "closed_lost",
        # --- منسوخ‌شده (فقط برای دوره‌ی گذار) ---
        "closed_won",
        "won",
        "lost",
    ]
    # الزامی هنگام وضعیت عدم فروش
    loss_reason: str | None = Field(default=None, max_length=50)
    # اختیاری، فقط برای فروش موفق (طبق سند: «اجازه‌ی ثبت» نه الزام)
    sale_amount: int | None = Field(default=None, ge=0)
    sold_products: str | None = Field(default=None, max_length=500)
    invoice_number: str | None = Field(default=None, max_length=50)
    resolution_notes: str | None = Field(default=None, max_length=500)
    # اقلام فروش ساختاریافته (فقط برای فروش موفق)
    sale_items: list[SaleItemInput] | None = None

    @field_validator("status", mode="before")
    @classmethod
    def normalize_deprecated_status(cls, value):
        """
        نرمال‌سازی نام‌های مستعار قدیمی پیش از هر اعتبارسنجی دیگری،
        تا کلاینت‌های قدیمی که هنوز «closed_won» می‌فرستند شکسته نشوند.
        """
        if isinstance(value, str):
            return DEPRECATED_STATUS_ALIASES.get(value, value)
        return value

    @model_validator(mode="after")
    def validate_loss_reason_required(self):
        if self.status == CLOSED_LOST_STATUS:
            if not self.loss_reason:
                raise ValueError(
                    "برای بستن پرونده به عنوان «عدم فروش»، ثبت دلیل الزامی است."
                )
            if self.loss_reason not in LOSS_REASONS:
                raise ValueError(
                    f"دلیل عدم فروش نامعتبر است. مقادیر مجاز: {', '.join(sorted(LOSS_REASONS))}"
                )
        return self

    @model_validator(mode="after")
    def validate_sale_items_only_on_won(self):
        if self.sale_items and self.status != FINAL_FACTOR_STATUS:
            raise ValueError(
                "اقلام فروش فقط هنگام ثبت وضعیت «فروش موفق» (final_factor) قابل ثبت هستند."
            )
        return self


class LeadCreateAttachedResponse(BaseModel):
    """
    پاسخِ ایمن برای زمانی که ثبت جدید به یک پرونده‌ی موجود متصل می‌شود
    اما پرونده متعلق به کاربر دیگری است. برخلاف LeadResponse، این مدل
    هیچ فیلد محرمانه‌ای از پرونده‌ی مالک اصلی (نام مشتری، نیاز، منبع،
    owner_id و ...) را افشا نمی‌کند — فقط تأیید می‌کند که ثبت درخواست
    به‌عنوان یک مورد تکراری پیوست شد. مالک اصلی جداگانه نوتیفای می‌شود.
    """
    status: str = "duplicate_attached"
    is_duplicate: bool = True
    message: str = (
        "این شماره قبلاً در سیستم ثبت شده است. درخواست شما به‌عنوان ثبت "
        "تکراری ضبط شد و به کارشناس مربوطه اطلاع داده شد."
    )


class LeadResponse(BaseModel):
    id: int
    customer_name: str
    mobile: str
    source: str
    need: str | None
    status: str
    created_by_id: int
    owner_id: int
    created_at: datetime
    updated_at: datetime
    last_contact_at: datetime | None = None
    next_follow_up: datetime | None = None
    last_assigned_at: datetime | None = None
    loss_reason: str | None = None
    sale_amount: int | None = None
    sold_products: str | None = None
    invoice_number: str | None = None
    resolution_notes: str | None = None
    is_escalated: bool = False
    # === فیلدهای اتصال لیدهای تکراری ===
    mobile_normalized: str | None = None
    duplicate_count: int = 0
    # محاسبه‌شده در زمان پاسخ‌دهی؛ ستون جداگانه‌ای در دیتابیس ندارد.
    is_open: bool = True
    health: str | None = None
    # قفل فاکتور: پس از ثبت، کارشناس اجازه‌ی ویرایش مبلغ/شماره فاکتور را ندارد
    is_invoice_locked: bool = False

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def compute_derived_fields(self):
        self.is_open = self.status not in CLOSED_STATUSES
        # فاکتور پس از رسیدن به وضعیت «فاکتور نهایی» قفل می‌شود
        self.is_invoice_locked = self.status == FINAL_FACTOR_STATUS
        if not self.is_open:
            self.health = None
            return self
        baseline = self.last_contact_at or self.created_at
        now = datetime.now(timezone.utc)
        if baseline.tzinfo is None:
            baseline = baseline.replace(tzinfo=timezone.utc)
        days_since = (now - baseline).total_seconds() / 86400
        if days_since <= 3:
            self.health = "healthy"          # 🟢 سالم
        elif days_since <= 7:
            self.health = "needs_attention"  # 🟡 نیاز به توجه
        elif days_since <= 14:
            self.health = "at_risk"          # 🟠 در خطر
        else:
            self.health = "critical"         # 🔴 بحرانی
        return self


class LeadSubmissionResponse(BaseModel):
    """
    یک ثبت تکراری متصل‌شده به پرونده‌ی اصلی؛ برای نمایش
    «previous submissions / duplicate history» در فرانت‌اند.
    """
    id: int
    lead_id: int
    submitted_by_id: int
    submitted_by_full_name: str | None = None
    customer_name: str
    mobile: str
    mobile_normalized: str | None = None
    need: str | None = None
    source: str | None = None
    notes: str | None = None
    submission_index: int
    matched_by: str
    submitted_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LeadAssign(BaseModel):
    owner_id: int
    note: str | None = None


class LeadFollowUpUpdate(BaseModel):
    next_follow_up: datetime | None = None


class PipelineStageCount(BaseModel):
    """تعداد پرونده‌ها در یک مرحله از قیف."""
    status: str
    count: int = 0


class PipelineCountsResponse(BaseModel):
    """
    خلاصه‌ی پایپ‌لاین برای نمایش مرحله‌به‌مرحله در فرانت‌اند:
    همه‌ی مراحل رسمی حتی با تعداد صفر برگردانده می‌شوند.
    """
    total: int = 0
    stages: list[PipelineStageCount] = Field(default_factory=list)
