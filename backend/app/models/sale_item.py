"""
===========================================================
مدل اقلام فروش (Sale Line Items)
-----------------------------------------------------------
هر ردیف، یک کالای فروخته‌شده با مبلغ ریالی آن در یک پرونده است.
مجموع مبالغ اقلام، مبلغ فروش همان پرونده را می‌سازد و تجمیع
این جدول به تفکیک کالا، نمودار «پرفروش‌ترین کالاها (ریال)»
را تولید می‌کند.

قید یکتایی (lead_id, product_id): برای هر پرونده و هر کالا
فقط یک ردیف وجود دارد؛ ثبت مجدد همان کالا، مبلغ را ادغام می‌کند.
===========================================================
"""
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import UniqueConstraint
from sqlalchemy import func
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from app.database.base import Base


class SaleItem(Base):
    __tablename__ = "sale_line_items"
    __table_args__ = (
        UniqueConstraint(
            "lead_id",
            "product_id",
            name="uq_sale_line_items_lead_product",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    lead_id: Mapped[int] = mapped_column(
        ForeignKey("leads.id"),
        nullable=False,
        index=True,
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id"),
        nullable=False,
        index=True,
    )

    # مبلغ فروش این قلم به ریال
    amount: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
