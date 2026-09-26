"""
===========================================================
HadiFlow

تنظیمات پروژه

این فایل تمام تنظیمات پروژه را از فایل .env می‌خواند.

مزایا:

- اطلاعات حساس داخل کد قرار نمی‌گیرند.
- امکان تغییر تنظیمات بدون تغییر کد وجود دارد.
- مناسب برای محیط توسعه و سرور.
===========================================================
"""

import warnings

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    کلاس تنظیمات پروژه
    """

    # -----------------------------------------
    # اطلاعات کلی پروژه
    # -----------------------------------------
    PROJECT_NAME: str = "HadiFlow"

    VERSION: str = "0.1.0"

    DEBUG: bool = True

    SECRET_KEY: str

    ALGORITHM: str = "HS256"
    
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # -----------------------------------------
    # اطلاعات دیتابیس
    # -----------------------------------------
    DATABASE_URL: str

    # -----------------------------------------
    # اعتبار توکن تازه‌سازی (روز)
    # -----------------------------------------
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # -----------------------------------------
    # دامنه‌های مجاز CORS
    #
    # پیش از این فهرست داخل main.py هاردکد شده بود و در استقرار
    # واقعی بی‌صدا می‌شکست. حالا از .env خوانده می‌شود:
    #   CORS_ORIGINS=https://panel.example.com,https://admin.example.com
    # -----------------------------------------
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # -----------------------------------------
    # زمان‌بند: هنگام اجرای تست‌ها یا چند نمونه‌ی همزمان از سرویس باید
    # خاموش باشد تا چند موتور هم‌زمان روی یک داده کار نکنند.
    # -----------------------------------------
    ENABLE_SCHEDULER: bool = True

    @field_validator("SECRET_KEY")
    @classmethod
    def warn_weak_secret_key(cls, v: str) -> str:
        # Non-fatal on purpose: crashing existing deployments on upgrade
        # would be worse than warning. HS256 keys below 32 bytes violate
        # RFC 7518 guidance and are far easier to brute-force.
        if len(v.encode("utf-8")) < 32:
            warnings.warn(
                "SECRET_KEY is shorter than 32 bytes; generate one with: "
                "python -c \"import secrets; print(secrets.token_urlsafe(64))\"",
                stacklevel=2,
            )
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        """تبدیل رشته‌ی جداشده با کاما به فهرست تمیز."""
        return [
            origin.strip()
            for origin in self.CORS_ORIGINS.split(",")
            if origin.strip()
        ]

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
    )


# ===========================================================
# ساخت یک نمونه از تنظیمات
#
# از این به بعد در کل پروژه فقط از settings استفاده می‌کنیم.
# ===========================================================
settings = Settings()
