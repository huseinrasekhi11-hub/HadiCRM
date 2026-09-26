"""
===========================================================
مدل لیدها (Lead Model)
-----------------------------------------------------------
فیلدهای جدید این نسخه (اتصال لیدهای تکراری):
  * mobile_normalized: کلید نرمال‌شده‌ی موبایل برای کشف تکراری
  * customer_name_normalized: نام نرمال‌شده برای تطبیق دقیق‌تر
  * duplicate_count: شمارنده‌ی ثبت‌های تکراری متصل‌شده
===========================================================
"""
from datetime import datetime
from datetime import timezone

import pytz
from sqlalchemy import JSON
from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from app.database.base import Base


def get_tehran_time():
    return datetime.now(pytz.timezone("Asia/Tehran"))


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(primary_key=True)

    customer_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    mobile: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )

    # --------------------------------------------------------
    # Duplicate-integration normalized keys
    # --------------------------------------------------------
    mobile_normalized: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        index=True,
    )

    customer_name_normalized: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    # Number of repeated submissions attached to this lead
    duplicate_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    need: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="new",
    )

    created_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    last_contact_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    next_follow_up: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # --------------------------------------------------------
    # Soft delete
    # --------------------------------------------------------
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # --------------------------------------------------------
    # Legacy / phased columns (behavior preserved)
    # --------------------------------------------------------
    sla_notified = Column(Boolean, default=False)

    # ساختار آرایه‌ای برای چند نیازی
    needs_list = Column(JSON, default=list)

    # فاز ۴: علت از دست رفتن مشتری
    loss_reason = Column(String, nullable=True)

    # فاز ۶: SLA و رکود
    status_updated_at = Column(DateTime, default=get_tehran_time)
    stagnant_warned = Column(Boolean, default=False)
    is_escalated = Column(Boolean, default=False)

    # فاز ۷: امتیاز ارزش مشتری
    score = Column(Integer, default=0)

    # فرآیند یادآوری و ثبت نتیجه‌ی فروش
    last_assigned_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    sale_amount = Column(Integer, nullable=True)
    sold_products = Column(String(500), nullable=True)
    invoice_number = Column(String(50), nullable=True)
    resolution_notes = Column(String(500), nullable=True)
