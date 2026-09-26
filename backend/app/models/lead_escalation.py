"""
مدل ارجاع اضطراری به مدیر (Escalation)

طبق «قانون سوم» سیستم یادآوری: اگر ۳ روز از یک پرونده‌ی باز بگذرد
و هیچ فعالیتی روی آن ثبت نشود، پرونده باید به‌صورت خودکار از کارشناس
گرفته شده و به مدیر ارجاع داده شود.

این رویداد هم در Activity (برای نمایش در تایم‌لاین) و هم در این جدول
اختصاصی (برای گزارش‌گیری مدیریتی، مثل «چند پرونده این ماه ارجاع
اضطراری شده‌اند؟») ثبت می‌شود.
"""
from datetime import datetime
from datetime import timezone

from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from app.database.base import Base


ESCALATION_REASONS = {
    "no_activity_3_days",  # قانون ۳: عدم فعالیت به مدت ۳ روز
}


class LeadEscalation(Base):
    __tablename__ = "lead_escalations"

    id: Mapped[int] = mapped_column(primary_key=True)

    lead_id: Mapped[int] = mapped_column(
        ForeignKey("leads.id"),
        nullable=False,
        index=True,
    )

    escalated_from_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    escalated_to_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    reason: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="no_activity_3_days",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
