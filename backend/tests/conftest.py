"""
پیکربندی مشترک pytest.

بخش زیادی از مجموعه‌ی تست (test_leads_api.py، test_role_visibility.py،
test_dashboard_charts_api.py و ...) به یک دیتابیس PostgreSQL واقعی و
یک کاربر ادمین از پیش‌ساخته (09120000000 / Admin123!) نیاز دارند —
این‌ها تست یکپارچه‌سازی (integration) هستند، نه واحد.

اما صرفِ import شدن app.main برای هر تست (حتی test_jwt.py که هیچ
دیتابیسی لازم ندارد) از قبل به این متغیرهای محیطی نیاز دارد چون
Settings آن‌ها را الزامی تعریف کرده:
    SECRET_KEY, DATABASE_URL

پیش از این فایلی این مقادیر را برای محیط تست فراهم نمی‌کرد، یعنی
حتی `pytest tests/test_jwt.py` به‌تنهایی هم بدون export دستی متغیرها
شکست می‌خورد. این فایل مقادیر پیش‌فرض امن و بی‌خطر تزریق می‌کند —
اما فقط وقتی متغیر از قبل در محیط ست نشده باشد، تا در CI/استقرار
واقعی مقادیر واقعی override شوند.
"""
import os

os.environ.setdefault("SECRET_KEY", "test-only-secret-do-not-use-in-production")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg2://hadiflow:hadiflow123@localhost:5432/hadiflow_test",
)
# زمان‌بند در فرایند تست هرگز نباید روشن شود
os.environ.setdefault("ENABLE_SCHEDULER", "false")
