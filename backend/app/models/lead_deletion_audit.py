"""
===========================================================
ممیزی حذف لید (Silent Deletion Audit)
-----------------------------------------------------------
طبق فرآیند کسب‌وکار، هر کاربری که به پرونده‌ای دسترسی دارد
می‌تواند آن را حذف کند، اما کاربر هرگز نباید بداند که یک
ممیزی اختصاصی برای مدیر وجود دارد.

این جدول یک «عکس فوری» (Snapshot) کامل از پرونده در لحظه‌ی
حذف ذخیره می‌کند:
  * چه پرونده‌ای حذف شد (lead_id + snapshot کامل)
  * نام مشتری و موبایل در لحظه‌ی حذف
  * وضعیت قبلی پرونده (previous_status)
  * صاحب اصلی پرونده (owner_id + نام ثبت‌شده)
  * چه کسی حذف کرد (deleted_by_id + نام ثبت‌شده)
  * زمان حذف (deleted_at)
  * مبلغ فروش، شماره فاکتور و کالاهای فروخته‌شده

نکته‌ی معماری: این جدول عمداً کلید خارجی (FK) به users/leads
ندارد تا حتی در صورت حذف فیزیکی کاربر یا پاکسازی آینده‌ی
لیدها، سند ممیزی هرگز از بین نرود. نام‌ها نیز به‌صورت
اسنپ‌شات ذخیره می‌شوند تا گزارش مدیریتی همیشه کامل بماند.
===========================================================
"""
from datetime import datetime
from datetime import timezone

from sqlalchemy import JSON
from sqlalchemy import DateTime
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from app.database.base import Base


class LeadDeletionAudit(Base):
    __tablename__ = "lead_deletion_audits"

    id: Mapped[int] = mapped_column(primary_key=True)

    lead_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )

    # --------------------------------------------------------
    # اسنپ‌شات هویتی پرونده در لحظه‌ی حذف
    # --------------------------------------------------------
    customer_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    mobile: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    mobile_normalized: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    source: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    need: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    previous_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    loss_reason: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    # --------------------------------------------------------
    # اسنپ‌شات مالی پرونده در لحظه‌ی حذف
    # --------------------------------------------------------
    sale_amount: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    sold_products: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    invoice_number: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    # --------------------------------------------------------
    # مالک اصلی و ایجادکننده (بدون FK برای ماندگاری ممیزی)
    # --------------------------------------------------------
    owner_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
    )

    owner_full_name: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
    )

    created_by_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    # --------------------------------------------------------
    # چه کسی حذف کرد و چه زمانی
    # --------------------------------------------------------
    deleted_by_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )

    deleted_by_full_name: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
    )

    deleted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    # --------------------------------------------------------
    # وضعیت احیا (Restore)
    # --------------------------------------------------------
    restored_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    restored_by_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    # --------------------------------------------------------
    # اسنپ‌شات کامل JSON برای بازسازی دقیق پرونده
    # --------------------------------------------------------
    snapshot: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
    )
