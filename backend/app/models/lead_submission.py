"""
===========================================================
مدل ثبت‌های تکراری لید (Lead Submission History)
-----------------------------------------------------------
طبق فرآیند کسب‌وکار، وقتی یک لید با همان نام مشتری و همان
شماره موبایل دوباره ثبت می‌شود، نباید یک رکورد جداگانه و
ایجادشده به‌صورت جزیره‌ای ساخته شود؛ بلکه باید به پرونده‌ی
اصلی متصل شود و این «ثبت مجدد» به‌عنوان یک رکورد قابل گزارش
ذخیره گردد.

این جدول هر ثبت تکراری را نگه می‌دارد:
  * چه کسی ثبت کرد (submitted_by_id)
  * چه زمانی (submitted_at)
  * با چه داده‌هایی (customer_name/mobile/need/source/notes)
  * با چه روشی به پرونده‌ی اصلی وصل شد (matched_by)
  * چندمین ثبت تکراری است (submission_index)

پرونده‌ی اصلی (lead_id) دست‌نخورده باقی می‌ماند؛ بنابراین تمام
ارجاع‌ها، فعالیت‌ها، وضعیت‌ها و پیگیری‌های قبلی حفظ می‌شوند.
===========================================================
"""
from datetime import datetime
from datetime import timezone

from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from app.database.base import Base

# How the submission was matched to an existing lead
MATCHED_BY_MOBILE = "mobile"
MATCHED_BY_MOBILE_AND_NAME = "mobile_and_name"
MATCHED_BY_VALUES = {MATCHED_BY_MOBILE, MATCHED_BY_MOBILE_AND_NAME}


class LeadSubmission(Base):
    __tablename__ = "lead_submissions"

    id: Mapped[int] = mapped_column(primary_key=True)

    lead_id: Mapped[int] = mapped_column(
        ForeignKey("leads.id"),
        nullable=False,
        index=True,
    )

    submitted_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    # The raw values exactly as submitted
    customer_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    customer_name_normalized: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    mobile: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    mobile_normalized: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        index=True,
    )

    need: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    source: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # 1 = first duplicate, 2 = second duplicate, ...
    submission_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    matched_by: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
