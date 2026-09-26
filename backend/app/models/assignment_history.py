"""
مدل تاریخچه‌ی ارجاع پرونده (Assignment History)

طبق فرآیند کسب‌وکار، ارجاع یک عملیات یک‌باره نیست؛ یک پرونده ممکن است
بارها بین کارشناسان مختلف دست‌به‌دست شود. پیش از این، ارجاع فقط با
یک خط توضیحی داخل Activity.description ثبت می‌شد که قابل کوئری
ساختاریافته (مثلاً «چند بار این پرونده ارجاع شده؟») نبود.

این مدل هر ارجاع را به صورت یک رکورد مجزا و قابل گزارش‌گیری ذخیره می‌کند.
"""
from datetime import datetime
from datetime import timezone

from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from app.database.base import Base


class AssignmentHistory(Base):
    __tablename__ = "assignment_history"

    id: Mapped[int] = mapped_column(primary_key=True)

    lead_id: Mapped[int] = mapped_column(
        ForeignKey("leads.id"),
        nullable=False,
        index=True,
    )

    assigned_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    assigned_to_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    note: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True,
    )

    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
