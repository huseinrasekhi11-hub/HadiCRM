"""
اسکیمای اقلام فروش و نمودار پرفروش‌ترین کالاها
تمام مبالغ، عدد صحیح ریال هستند.
"""
from datetime import datetime

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field


class SaleItemInput(BaseModel):
    """یک قلم فروش؛ برای ثبت همراه با تغییر وضعیت یا الحاق بعدی."""
    product_id: int
    amount: int = Field(ge=0, description="مبلغ به ریال")


class SaleItemCreate(SaleItemInput):
    """ورودی اندپوینت الحاق قلم فروش."""
    pass


class SaleItemResponse(BaseModel):
    id: int
    lead_id: int
    product_id: int
    product_name: str | None = None
    amount: int
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class TopProductRow(BaseModel):
    """یک ردیف از نمودار پرفروش‌ترین کالاها."""
    product_id: int
    product_name: str
    total_sales: int = 0
    lead_count: int = 0


class TopProductsResponse(BaseModel):
    """
    پاسخ کامل نمودار کالاها:
      * products: جمع فروش ریالی هر کالا (شامل کالاهای بدون فروش)
      * total_sales: مجموع فروش ساختاریافته‌ی همه‌ی کالاها
      * unattributed_amount: مبلغ فروش‌های موفقِ فاقد قلم ساختاریافته
        (داده‌ی تاریخی/متن آزاد) — برای شفافیت گزارش، نه تجمیع حدسی
    """
    products: list[TopProductRow] = Field(default_factory=list)
    total_sales: int = 0
    unattributed_amount: int = 0
