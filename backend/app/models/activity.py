from datetime import datetime
from datetime import timezone

from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from app.database.base import Base


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(primary_key=True)

    lead_id: Mapped[int] = mapped_column(
        ForeignKey("leads.id"),
        nullable=False,
        index=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    activity_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    # === فیلدهای جدید: نتیجه‌ی اقدام و پیگیری اجباری بعدی ===
    # نتیجه‌ی اقدام (مثلاً: پاسخ نداد / علاقه‌مند / شماره اشتباه / عدم علاقه)
    outcome: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    # زمان پیگیری بعدی که هنگام ثبت این اقدام تعیین شده است
    next_follow_up: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # در صورت انتخاب «بدون پیگیری»، دلیل آن باید ثبت شود
    no_followup_reason: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
