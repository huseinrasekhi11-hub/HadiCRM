# Changelog


تمام تغییرات پروژه HadiFlow داخل این فایل ثبت خواهد شد.

---

## Version 0.0.1

شروع پروژه

- ایجاد ساختار اولیه
- ایجاد Repository
- ایجاد معماری پروژه

---

## Version 0.2.0 — پیاده‌سازی کامل گزارش ممیزی + قانون ۴

### امنیت
- چرخش و ابطال سمت‌سرور refresh token (جدول refresh_sessions، تشخیص replay، خانواده‌ی نشست)
- اندپوینت POST /auth/logout (ابطال واقعی نشست)
- محدودسازی نرخ ورود (۴۲۹ + Retry-After) برای brute-force/credential stuffing
- ستون canonical شماره موبایل کاربر + لاگین با هر فرمت معادل
- قفل advisory برای jobهای زمان‌بند در استقرار چند worker
- پاسخ یکسان ۴۰۱ برای حساب غیرفعال (رفع enumeration)
- DEBUG=False پیش‌فرض؛ SECRET_KEY زیر ۳۲ بایت = خطای استارت‌آپ
- لاگ ساختاریافته برای شکست نوشتن audit log

### صحت/پایداری
- GET /health با بررسی واقعی دیتابیس (healthcheckهای Docker به آن سوییچ شدند)
- Vary: Authorization روی پاسخ‌های ETag احراز هویتی‌شده
- مرزهای زمانی داشبورد بر مبنای روز تقویمی تهران؛ date_to فقط-تاریخ فراگیر
- downgrade بیس‌لاین Alembic غیرقابل‌بازگشت (جلوگیری از حذف جداول تولید)
- downgrade مهاجرت فیلدهای کاربر فقط ستون‌های خودش را برمی‌دارد
- پاک‌سازی فایل آپلودشده در صورت شکست ثبت DB
- jdatetime → 5.3.0

### فیچر
- قانون ۴: نوتیفیکیشن follow_up_due هنگام سررسید next_follow_up (پرچم یک‌بارمصرف follow_up_notified)
- میدل‌ور مستقل security_headers
- CI گیت‌های کامل (pytest روی Postgres ۱۵ + lint + build)
