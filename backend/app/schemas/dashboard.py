"""
اسکیمای نمودارهای تحلیلی داشبورد مدیریت
پاسخ‌ها برای مصرف مستقیم فرانت‌اند (رسم نمودار) طراحی شده‌اند:
  * مقادیر پولی همیشه عدد صحیح (ریال) هستند
  * برچسب‌ها به‌صورت متن آماده‌ی نمایش برگردانده می‌شوند
"""
from pydantic import BaseModel


class ChartPoint(BaseModel):
    """یک نقطه از نمودار زمانی (مثلاً فروش روزانه یا روند فروش)."""
    label: str
    amount: int = 0
    count: int = 0


class SalesByUserRow(BaseModel):
    """عملکرد مالی یک کارشناس: مبلغ فروش، تعداد برد و میانگین."""
    user_id: int
    full_name: str | None = None
    won_count: int = 0
    total_sales: int = 0
    average_sale: int = 0


class LeadsByUserRow(BaseModel):
    """توزیع پرونده‌های هر کارشناس: کل / باز / برد / باخت."""
    user_id: int
    full_name: str | None = None
    total_leads: int = 0
    open_leads: int = 0
    won_leads: int = 0
    lost_leads: int = 0


class ConversionStats(BaseModel):
    """آمار کلان قیف: تعداد کل و نرخ تبدیل."""
    total_leads: int = 0
    open_leads: int = 0
    won_leads: int = 0
    lost_leads: int = 0
    conversion_rate: float = 0.0


class ReferralsReceivedRow(BaseModel):
    """تعداد ارجاع‌های دریافت‌شده توسط یک کاربر."""
    user_id: int
    full_name: str | None = None
    received_count: int = 0


class ReferralPairRow(BaseModel):
    """تعداد ارجاع‌ها بین یک جفت کاربر (از → به)."""
    from_user_id: int
    from_full_name: str | None = None
    to_user_id: int
    to_full_name: str | None = None
    count: int = 0
