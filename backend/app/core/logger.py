"""
===========================================================
HadiFlow

سیستم ثبت لاگ پروژه

تمام پیام‌های مهم پروژه از این فایل ثبت می‌شوند.
===========================================================
"""

from loguru import logger
import sys

# حذف تنظیمات پیش‌فرض
logger.remove()

# نمایش لاگ در ترمینال
logger.add(
    sys.stdout,
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
           "<level>{level}</level> | "
           "<cyan>{message}</cyan>",
)

# ذخیره لاگ در فایل
logger.add(
    "logs/hadiflow.log",
    rotation="10 MB",
    retention="30 days",
    level="INFO",
    encoding="utf-8",
)

app_logger = logger
