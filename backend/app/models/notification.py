"""
مدل نوتیفیکیشن داخلی (Dashboard Notification)
پیش از این، اندپوینت /notifications/ فقط یک خلاصه‌ی شمارشی
(تعداد وظایف عقب‌افتاده و لیدهای من) برمی‌گرداند و هیچ رکورد
واقعی و قابل-خواندن/نشده‌ای در دیتابیس ذخیره نمی‌شد.
این مدل، نوتیفیکیشن‌های واقعی را ذخیره می‌کند تا:
قانون ۱ (یادآوری ۶۰ دقیقه‌ای)
قانون ۳ (ارجاع به مدیر پس از ۳ روز)
بتوانند نوتیفیکیشن داشبورد ایجاد کنند که کاربر آن را می‌بیند و می‌خواند.
"""
from datetime import datetime
from datetime import timezone

from sqlalchemy import Boolean
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from app.database.base import Base

NOTIFICATION_TYPES = {
    "no_contact_reminder",    # قانون ۱: ۶۰ دقیقه از ارجاع گذشته و اقدامی ثبت نشده
    "daily_followup_digest",  # قانون ۲: خلاصه‌ی صبحگاهی پرونده‌های باز
    "lead_escalated",         # قانون ۳: پرونده به مدیر ارجاع داده شد (برای کارشناس)
    "lead_escalated_manager", # قانون ۳: پرونده‌ای به شما ارجاع داده شد (برای مدیر)
    "lead_assigned",          # ارجاع/ارجاع مجدد پرونده
    "duplicate_submission",   # ثبت تکراری برای پرونده‌ی این کاربر ثبت شد
}


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    lead_id: Mapped[int | None] = mapped_column(
        ForeignKey("leads.id"),
        nullable=True,
        index=True,
    )

    notification_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    message: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    is_read: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
