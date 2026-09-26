"""
===========================================================
مدل محصولات (Product Catalog)
-----------------------------------------------------------
فهرست رسمی کالاهای قابل فروش. پیش از این، کالاهای فروخته‌شده
به‌صورت متن آزاد داخل leads.sold_products ذخیره می‌شدند و
هیچ‌گونه تجمیع قابل‌اتکا «به تفکیک کالا و به ریال» ممکن نبود.

این جدول به‌همراه جدول اقلام فروش (sale_line_items) امکان
گزارش «پرفروش‌ترین کالاها به ریال» را فراهم می‌کند.
===========================================================
"""
from datetime import datetime

from sqlalchemy import Boolean
from sqlalchemy import DateTime
from sqlalchemy import String
from sqlalchemy import func
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from app.database.base import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
