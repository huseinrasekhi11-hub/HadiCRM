# ============================================================
#                       HadiFlow CRM
# ============================================================

## معرفی پروژه

HadiFlow یک سیستم CRM اختصاصی برای شرکت هادی تهویه است.

این پروژه با هدف مدیریت کامل چرخه فروش، مشتریان،
لیدها، خدمات پس از فروش و گزارش‌های مدیریتی طراحی شده است.

---

## اهداف پروژه

- مدیریت مشتریان
- مدیریت لیدها
- مدیریت فرصت‌های فروش
- مدیریت پروژه‌ها
- سیستم ارجاع بین کارشناسان
- سیستم یادآوری هوشمند
- اتصال به ربات بله
- داشبورد مدیریتی
- KPI و گزارش‌های تحلیلی

---

## تکنولوژی‌های استفاده شده

Backend

- Python 3.11 (CI/Docker baseline)
- FastAPI

Database

- PostgreSQL

Cache

- PostgreSQL-backed shared rate limiting; no Redis dependency is required by the current repository

ORM

- SQLAlchemy 2

Migration

- Alembic

Scheduler

- APScheduler

Container

- Docker

Version Control

- Git

---

## ساختار پروژه

app/

تمام کدهای اصلی پروژه

docs/

مستندات

tests/

تست‌ها

scripts/

اسکریپت‌های کمکی

docker/

تنظیمات Docker

---

## استقرار و مرزهای امنیتی (Deployment & Security Boundaries)

### TLS / Reverse Proxy — الزامی برای تولید

`docker-compose.yml` پورت `8000` سرویس API را مستقیماً روی میزبان
publish می‌کند و **TLS در این مخزن terminate نمی‌شود**. این طراحی
عمدی است: انتظار می‌رود در تولید، یک reverse proxy / load balancer
(nginx، Caddy، Traefik یا سرویس مدیریت‌شده) جلوی API بنشیند و:

1. TLS (HTTPS) را terminate کند؛
2. هدر `X-Forwarded-For` را به‌درستی ست کند (rate limiter لاگین به آن
   تکیه می‌کند)؛
3. در صورت امکان پورت 8000 را فقط از همان proxy قابل‌دسترس کند
   (مثلاً bind به `127.0.0.1:8000:8000` در compose وقتی proxy روی
   همان میزبان است).

هرگز این compose را بدون لایه‌ی TLS مستقیماً روی اینترنت عمومی
قرار ندهید — توکن‌های JWT و رمزهای عبور بدون رمزنگاری منتقل می‌شوند.

### چند نمونه‌ای (multi-worker / multi-replica)

- **Scheduler:** هر فرایند API که `ENABLE_SCHEDULER=true` دارد،
  jobها را اجرا می‌کند. jobها اکنون با `pg_try_advisory_lock` محافظت
  می‌شوند (در هر لحظه فقط یک نمونه هر job را اجرا می‌کند)، ولی برای
  کاهش کار تکراری در استقرار چندنسخه‌ای همچنان توصیه می‌شود روی
  همه‌ی نمونه‌ها به‌جز یکی `ENABLE_SCHEDULER=false` تنظیم شود.
- **Rate limiter لاگین:** در حافظه‌ی هر فرایند است؛ با N replica
  بودجه‌ی مجاز عملاً N برابر می‌شود. برای استقرار بزرگ، throttling
  مشترک (Redis یا edge/gateway) جلوی سرویس اضافه کنید.

### توکن‌ها در مرورگر

- **Refresh token:** فقط در کوکی `HttpOnly` + `Secure` + `SameSite` نگهداری می‌شود و در پاسخ JSON بازگردانده نمی‌شود. درخواست‌های cookie-authenticated برای refresh/logout با کنترل CSRF محافظت می‌شوند.
- **Access token:** فقط در حافظه‌ی JavaScript نگهداری می‌شود؛ بعد از reload دوباره از refresh cookie صادر می‌شود.
- هیچ توکن محرمانه‌ای در `localStorage` یا `sessionStorage` ذخیره نمی‌شود؛ فقط یک marker غیرحساس برای همگام‌سازی تب‌ها باقی می‌ماند.
- اگر پنل از API با origin جداگانه استفاده می‌کند، HTTPS، `credentials` و `CORS_ORIGINS` باید مطابق تنظیمات production پیکربندی شوند.

---

## نویسندگان

Project Owner

Mahan Hasani

Technical Architecture

OpenAI GPT-5.5