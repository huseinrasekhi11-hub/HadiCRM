"""
روتر داشبورد
-----------------------------------------------------------
  * GET /dashboard/                   → داشبورد نقش‌محور
  * GET /dashboard/charts/*           → نمودارهای تحلیلی، فقط ادمین/مدیرعامل

انتخاب داشبورد:
  نقش‌های نظارتی (ادمین/مدیرعامل/مدیر/مدیر فروش) داشبورد مدیریتی
  می‌گیرند؛ سایر نقش‌ها داشبورد کارشناسی (محدود به پرونده‌های خودشان).
"""
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.constants.roles import Roles
from app.core import jalali
from app.core.jalali import parse_jalali_date
from app.crud.dashboard import (
    get_conversion_stats,
    get_daily_sales,
    get_leads_by_user,
    get_manager_dashboard,
    get_referrals_between_users,
    get_referrals_received,
    get_sales_by_user,
    get_sales_trend,
    get_salesperson_dashboard,
)
from app.crud.sale_item import get_top_products_stats
from app.database.database import get_db
from app.models.user import User
from app.permissions.permission import can_view_all_leads, require_roles
from app.schemas.dashboard import (
    ChartPoint,
    ConversionStats,
    LeadsByUserRow,
    ReferralPairRow,
    ReferralsReceivedRow,
    SalesByUserRow,
)
from app.schemas.sale_item import TopProductsResponse

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"],
)

# وابستگی مشترک: نمودارهای تحلیلی فقط برای ادمین/مدیرعامل
CHART_PERMISSIONS = [
    Depends(
        require_roles(
            Roles.ADMIN,
            Roles.CEO,
        )
    )
]

CalendarChoice = Literal["jalali", "gregorian"]


def _parse_datetime_bound(
    value: str | None,
    inclusive_end: bool = False,
) -> datetime | None:
    """
    پارس کران‌های زمانی با پشتیبانی دوگانه:
      * میلادی: 2026-08-01 یا 2026-08-01T10:30:00
      * جلالی:  1405/05/10 یا 1405-05-10 (اختیاری با ساعت 1405/05/10 15:30)

    ورودی‌های «فقط-تاریخ» به‌عنوان روز تقویمیِ تهران تفسیر می‌شوند
    (ستون تحلیلی status_updated_at naive و به وقت تهران ذخیره می‌شود).
    با inclusive_end=True کرانِ پایان به نیمه‌شبِ «روز بعد» منتقل می‌شود
    تا date_to فقط-تاریخ، کلِ روزِ پایان را فراگیر پوشش دهد؛ پیش از این
    نیمه‌شبِ همان روز مرزِ «کوچک‌تر» بود و کل روزِ درخواستی کاربر از
    نمودار حذف می‌شد. datetime با ساعتِ صریح دقیقاً همان‌جا برش می‌خورد.
    """
    if not value:
        return None

    text = value.strip()
    date_only = "T" not in text and " " not in text

    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            if date_only:
                # روز تقویمی تهران: نیمه‌شبِ تهران، نه نیمه‌شبِ UTC
                if inclusive_end:
                    parsed = parsed + timedelta(days=1)
                return jalali.TEHRAN_TZ.localize(parsed).astimezone(timezone.utc)
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        pass

    try:
        parsed = parse_jalali_date(text)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid date value '{value}'. "
                "Use ISO format (2026-08-01) or Jalali format (1405/05/10)."
            ),
        )
    # parse_jalali_date خروجی UTC-aware بر مبنای نیمه‌شب تهران می‌دهد
    if inclusive_end and date_only:
        parsed = parsed + timedelta(days=1)
    return parsed


@router.get("/")
def dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if can_view_all_leads(current_user):
        return get_manager_dashboard(db, current_user)
    return get_salesperson_dashboard(db, current_user)


@router.get(
    "/charts/daily-sales",
    response_model=list[ChartPoint],
    dependencies=CHART_PERMISSIONS,
)
def chart_daily_sales(
    days: int = Query(30, ge=1, le=365, description="تعداد روزهای گذشته"),
    calendar: CalendarChoice = Query(
        "gregorian",
        description="تقویم برچسب‌ها و دانه‌بندی: میلادی یا جلالی",
    ),
    date_from: str | None = Query(
        None,
        description="شروع بازه (میلادی یا جلالی)؛ جایگزین days",
    ),
    date_to: str | None = Query(
        None,
        description="پایان بازه (میلادی یا جلالی، شامل همان روز)؛ جایگزین days",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """فروش روزانه (ریال) — روزهای بدون فروش با صفر پر می‌شوند."""
    return get_daily_sales(
        db,
        days=days,
        calendar=calendar,
        date_from=_parse_datetime_bound(date_from),
        date_to=_parse_datetime_bound(date_to, inclusive_end=True),
    )


@router.get(
    "/charts/sales-by-user",
    response_model=list[SalesByUserRow],
    dependencies=CHART_PERMISSIONS,
)
def chart_sales_by_user(
    days: int | None = Query(
        None,
        ge=1,
        le=3650,
        description="پنجره‌ی زمانی اختیاری؛ بدون مقدار = کل تاریخچه",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """مبلغ فروش، تعداد فروش موفق و میانگین فروش هر کارشناس (ریال)."""
    return get_sales_by_user(db, days=days)


@router.get(
    "/charts/leads-by-user",
    response_model=list[LeadsByUserRow],
    dependencies=CHART_PERMISSIONS,
)
def chart_leads_by_user(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """تعداد کل پرونده‌های هر کاربر به تفکیک باز / برد / باخت."""
    return get_leads_by_user(db)


@router.get(
    "/charts/conversion",
    response_model=ConversionStats,
    dependencies=CHART_PERMISSIONS,
)
def chart_conversion(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """تعداد کل پرونده‌ها و نرخ تبدیل (برد از کل پرونده‌های بسته‌شده)."""
    return get_conversion_stats(db)


@router.get(
    "/charts/referrals-received",
    response_model=list[ReferralsReceivedRow],
    dependencies=CHART_PERMISSIONS,
)
def chart_referrals_received(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """رتبه‌بندی کاربران بر اساس تعداد ارجاع‌های دریافت‌شده."""
    return get_referrals_received(db)


@router.get(
    "/charts/referrals-between-users",
    response_model=list[ReferralPairRow],
    dependencies=CHART_PERMISSIONS,
)
def chart_referrals_between_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """تعداد ارجاع‌ها بین هر جفت کاربر (ارجاع‌دهنده → ارجاع‌گیرنده)."""
    return get_referrals_between_users(db)


@router.get(
    "/charts/sales-trend",
    response_model=list[ChartPoint],
    dependencies=CHART_PERMISSIONS,
)
def chart_sales_trend(
    days: int = Query(90, ge=7, le=1095, description="بازه‌ی بررسی"),
    granularity: Literal["day", "week", "month"] = Query(
        "day",
        description="دانه‌بندی نمودار: روز / هفته / ماه",
    ),
    calendar: CalendarChoice = Query(
        "gregorian",
        description="تقویم برچسب‌ها و دانه‌بندی: میلادی یا جلالی",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    روند فروش در زمان با دانه‌بندی قابل انتخاب.
    در حالت جلالی، هفته‌ها شنبه‌مبنا (هفته‌ی ایرانی) هستند.
    """
    return get_sales_trend(db, days=days, granularity=granularity, calendar=calendar)


@router.get(
    "/charts/top-products",
    response_model=TopProductsResponse,
    dependencies=CHART_PERMISSIONS,
)
def chart_top_products(
    days: int | None = Query(
        None,
        ge=1,
        le=3650,
        description="پنجره‌ی زمانی اختیاری؛ بدون مقدار = کل تاریخچه",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    پرفروش‌ترین کالاها به ریال.
    فقط فروش‌های موفق دارای اقلام ساختاریافته تجمیع می‌شوند؛
    فروش‌های تاریخی بدون قلم، در unattributed_amount گزارش می‌شوند.
    """
    return get_top_products_stats(db, days=days)
