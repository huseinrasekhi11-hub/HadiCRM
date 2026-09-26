"""
===========================================================
HadiFlow
ابزارهای تقویم جلالی (هجری شمسی) و منطقه‌زمانی ایران
-----------------------------------------------------------
این ماژول تنها مرجع تاریخ جلالی در کل بک‌اند است:
  * تبدیل میلادی <-> جلالی
  * فرمت‌دهی جلالی: 1405/05/01 و 1405/05/01 15:30
  * پارس رشته‌های جلالی به datetime آگاه از منطقه‌زمانی (UTC)
  * کران‌های روز جلالی برای گروه‌بندی و فیلتر نمودارها/گزارش‌ها
  * کران‌های «امروزِ تهران» برای فیلترهای پیگیری

قانون مهم و مستند:
  هر timestamp «naive» ذخیره‌شده در دیتابیس، زمان محلی تهران
  تفسیر می‌شود. ستون leads.status_updated_at (مبنای تاریخ فروش)
  دقیقاً به همین شکل نوشته می‌شود (پیش‌فرض get_tehran_time).
  ستون‌های aware (مثل created_at) که UTC ذخیره می‌شوند، به‌درستی
  تبدیل می‌شوند.
===========================================================
"""
from datetime import datetime
from datetime import timedelta
from datetime import timezone

import jdatetime
import pytz

# منطقه‌زمانی رسمی ایران
TEHRAN_TZ = pytz.timezone("Asia/Tehran")

_JALALI_SEPARATORS = ("/", "-")


# ---------------------------------------------------------------
# نرمال‌سازی آگاهی منطقه‌زمانی
# ---------------------------------------------------------------
def ensure_aware(dt: datetime | None, naive_tz=TEHRAN_TZ) -> datetime | None:
    """
    اگر datetime بدون منطقه‌زمانی باشد، آن را زمان محلی تهران فرض می‌کند
    (طبق قانون مستند بالا) و آگاه برمی‌گرداند.
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return naive_tz.localize(dt)


def to_tehran(dt: datetime | None) -> datetime | None:
    """تبدیل هر تاریخ معتبری به زمان آگاهِ تهران."""
    aware = ensure_aware(dt)
    if aware is None:
        return None
    return aware.astimezone(TEHRAN_TZ)


def naive_tehran_now() -> datetime:
    """اکنونِ تهران به‌صورت naive — برای کوئری روی ستون‌های naive."""
    return datetime.now(TEHRAN_TZ).replace(tzinfo=None)


def naive_tehran_from_utc(dt: datetime) -> datetime:
    """تبدیل یک زمان آگاه به naiveِ معادل در زمان محلی تهران."""
    return ensure_aware(dt).astimezone(TEHRAN_TZ).replace(tzinfo=None)


# ---------------------------------------------------------------
# تبدیل و فرمت‌دهی جلالی
# ---------------------------------------------------------------
def to_jalali_date(dt: datetime) -> jdatetime.date:
    """تبدیل هر datetime به تاریخ جلالی (بر مبنای زمان تهران)."""
    tehran = to_tehran(dt)
    return jdatetime.date.fromgregorian(date=tehran.date())


def format_jalali_date(dt: datetime) -> str:
    """فرمت تاریخ جلالی: 1405/05/01"""
    j = to_jalali_date(dt)
    return f"{j.year:04d}/{j.month:02d}/{j.day:02d}"


def format_jalali_month(dt: datetime) -> str:
    """فرمت ماه جلالی: 1405/05"""
    j = to_jalali_date(dt)
    return f"{j.year:04d}/{j.month:02d}"


def format_jalali_datetime(dt: datetime) -> str:
    """فرمت تاریخ‌زمان جلالی: 1405/05/01 15:30"""
    tehran = to_tehran(dt)
    # jdatetime.datetime.fromgregorian does NOT support a `time=` keyword;
    # it is silently ignored and a bare date falls into the AttributeError
    # branch that builds midnight. Pass the full aware datetime instead.
    j = jdatetime.datetime.fromgregorian(datetime=tehran)
    return (
        f"{j.year:04d}/{j.month:02d}/{j.day:02d} "
        f"{j.hour:02d}:{j.minute:02d}"
    )


def format_jalali_label(j_date: jdatetime.date) -> str:
    """برچسب تاریخ جلالی از روی خودِ شیء jdatetime.date."""
    return f"{j_date.year:04d}/{j_date.month:02d}/{j_date.day:02d}"


# ---------------------------------------------------------------
# پارس رشته‌های جلالی
# ---------------------------------------------------------------
def parse_jalali_date(value: str) -> datetime:
    """
    پارس رشته‌ی جلالی به datetime آگاه (خروجی: UTC).

    فرمت‌های قابل قبول:
      1405/05/01          -> نیمه‌شبِ آن روز به وقت تهران
      1405-05-01
      1405/05/01 15:30

    در صورت نامعتبر بودن، ValueError پرتاب می‌شود.
    """
    if not value or not isinstance(value, str):
        raise ValueError("Empty date value.")

    text = value.strip()
    date_part, time_part = text, None
    if " " in text:
        date_part, time_part = text.split(" ", 1)

    separator = next((s for s in _JALALI_SEPARATORS if s in date_part), None)
    if separator is None:
        raise ValueError(f"Unrecognized Jalali date format: {value}")

    parts = date_part.split(separator)
    if len(parts) != 3:
        raise ValueError(f"Unrecognized Jalali date format: {value}")

    try:
        j_year, j_month, j_day = (int(part) for part in parts)
        j_date = jdatetime.date(j_year, j_month, j_day)
    except (ValueError, TypeError) as error:
        raise ValueError(f"Invalid Jalali date: {value}") from error

    hour = 0
    minute = 0
    if time_part:
        try:
            hour_text, minute_text = time_part.split(":")[:2]
            hour = int(hour_text)
            minute = int(minute_text)
        except (ValueError, TypeError) as error:
            raise ValueError(f"Invalid time in Jalali datetime: {value}") from error

    g_date = j_date.togregorian()
    naive = datetime(g_date.year, g_date.month, g_date.day, hour, minute)
    return TEHRAN_TZ.localize(naive).astimezone(timezone.utc)


# ---------------------------------------------------------------
# کران‌های زمانی جلالی / تهران
# ---------------------------------------------------------------
def jalali_day_bounds_utc(j_date: jdatetime.date):
    """
    شروع و پایان یک روز جلالی به وقت تهران، برگردانده‌شده به UTC.
    """
    g_date = j_date.togregorian()
    start = TEHRAN_TZ.localize(datetime(g_date.year, g_date.month, g_date.day))
    end = TEHRAN_TZ.normalize(start + timedelta(days=1))
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def jalali_today_bounds_utc():
    """
    کران‌های «امروز» بر اساس روز جلالیِ منطقه‌زمانی تهران (نه UTC).
    برای فیلترهای «پیگیری‌های امروز» استفاده می‌شود.
    """
    now_naive_tehran = naive_tehran_now()
    start_naive = now_naive_tehran.replace(hour=0, minute=0, second=0, microsecond=0)
    start = TEHRAN_TZ.localize(start_naive)
    end = TEHRAN_TZ.normalize(start + timedelta(days=1))
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def jalali_week_start(j_date: jdatetime.date) -> jdatetime.date:
    """
    شروع هفته‌ی ایرانی (شنبه) برای تاریخ جلالی داده‌شده.
    در jdatetime مقدار 0 برای weekday() همان شنبه است.
    """
    return j_date - jdatetime.timedelta(days=j_date.weekday())
