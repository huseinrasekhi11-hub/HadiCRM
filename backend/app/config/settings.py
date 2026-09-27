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

    # SECURITY: پیش‌فرض امن (False). در توسعه به‌صراحت در .env
    # DEBUG=true گذاشته شود؛ فراموش‌کردن آن در استقرار دیگر باعث
    # روشن‌ماندن حالت debug نمی‌شود.
    DEBUG: bool = False

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
    # کوکیِ توکن تمدید (HttpOnly)
    #
    # توکن تمدید در کوکیِ HttpOnly نگه داشته می‌شود تا جاوااسکریپتِ
    # مخرب (XSS) نتواند آن را بخواند (localStorage برای هیچ اسکریپتی
    # قابل‌خواندن نیست، اما کوکیِ HttpOnly هست — نه). تنظیمات زیر برای
    # استقرارهای مختلف قابل تنظیم‌اند:
    #   * REFRESH_COOKIE_SAMESITE=none → وقتی فرانت‌اند و بک‌اند روی
    #     دامنه‌های متفاوت‌اند (مثل panel.example.com + api.example.com)؛
    #     در این حالت REFRESH_COOKIE_SECURE حتماً باید true باشد.
    #   * REFRESH_COOKIE_SAMESITE=lax  → وقتی هر دو روی یک سایت‌اند (پیشنهاد:
    #     فرانت‌اند را پشت یک reverse-proxy/rewrite روی همان دامنه سرو کنید).
    # -----------------------------------------
    REFRESH_COOKIE_NAME: str = "hadiflow_refresh"
    REFRESH_COOKIE_PATH: str = "/auth"
    REFRESH_COOKIE_SECURE: bool = True
    REFRESH_COOKIE_SAMESITE: str = "none"
    REFRESH_COOKIE_DOMAIN: str | None = None

    # -----------------------------------------
    # زمان‌بند: هنگام اجرای تست‌ها یا چند نمونه‌ی همزمان از سرویس باید
    # خاموش باشد تا چند موتور هم‌زمان روی یک داده کار نکنند.
    # -----------------------------------------
    ENABLE_SCHEDULER: bool = True

    # -----------------------------------------
    # محدودسازی نرخ ورود (brute-force control)
    # پنجره‌ی لغزنده؛ جزئیات در app/core/rate_limit.py
    # -----------------------------------------
    LOGIN_RATE_WINDOW_SECONDS: int = 900
    LOGIN_MAX_FAILURES_PER_ACCOUNT: int = 5
    LOGIN_MAX_FAILURES_PER_IP: int = 30

    # بودجه‌ی حدسِ «رمز فعلی» در اندپوینت تغییر رمز (همان مدلِ پنجره)
    PASSWORD_CHANGE_MAX_FAILURES: int = 5
    PASSWORD_CHANGE_WINDOW_SECONDS: int = 900

    # انبارِ شمارنده‌های محدودسازِ ورود:
    #   auto (پیش‌فرض) → دیتابیسِ مشترک + میانبرِ حافظه‌ای
    #   db             → فقط دیتابیسِ مشترک
    #   memory         → فقط حافظه‌ی همین فرایند (توصیه نمی‌شود مگر اینکه
    #                    throttle اصلی در لبه/درگاه انجام شود؛ با چند
    #                    worker/replica سقفِ مؤثر ضربدر تعداد نمونه‌ها می‌شود)
    LOGIN_RATE_BACKEND: str = "auto"

    @field_validator("SECRET_KEY")
    @classmethod
    def require_strong_secret_key(cls, v: str) -> str:
        # SECURITY: پیش از این فقط warning داده می‌شد؛ یعنی استقرار می‌توانست
        # با کلید ضعیف بالا بیاید و کسی متوجه نشود. کلید HS256 کوتاه‌تر از
        # ۳۲ بایت طبق RFC 7518 نامعتبر است و brute-force آن آسان است.
        # حالا برنامه با کلید ضعیف اصلاً استارت نمی‌شود (fail fast).
        if len(v.encode("utf-8")) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 UTF-8 bytes; generate one with: "
                'python -c "import secrets; print(secrets.token_urlsafe(64))"'
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
