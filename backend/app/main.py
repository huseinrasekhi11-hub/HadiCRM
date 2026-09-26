"""
===========================================================
HadiFlow
نقطه شروع اجرای پروژه
هر زمان سرور اجرا شود، این فایل اولین فایل اجرا شده است.
وظایف این فایل:
1- ساخت برنامه FastAPI
2- تنظیم اطلاعات پروژه
3- ثبت Router ها
4- راه‌اندازی اولیه سیستم
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DataError, IntegrityError

from app.api.routes.admin_lead_history import router as admin_lead_history_router
from app.api.routes.audit_logs import router as audit_logs_router
from app.api.routes.auth import router as auth_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.deleted_leads import router as deleted_leads_router
from app.api.routes.leads import router as leads_router
from app.api.routes.notifications import router as notifications_router
from app.api.routes.products import router as products_router
from app.api.routes.tasks import router as tasks_router
from app.api.routes.users import public_users_router
from app.api.routes.users import router as users_router
from app.config.settings import settings
from app.core.logger import app_logger
from app.middleware.etag import ETagMiddleware
from app.scheduler.jobs import start_scheduler

# ===========================================================
# چرخه‌ی عمر برنامه (جایگزین on_event که منسوخ شده است)
# ===========================================================
@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.ENABLE_SCHEDULER:
        start_scheduler()
        app_logger.info("Scheduler started")
    else:
        app_logger.info("Scheduler disabled via ENABLE_SCHEDULER=false")
    yield


# ===========================================================
# ساخت شیء اصلی برنامه
# ===========================================================
app = FastAPI(
    title="HadiFlow",
    description="CRM & Workflow Management System",
    version=settings.VERSION,
    lifespan=lifespan,
)

# ===========================================================
# CORS
# اجازه دسترسی به پنل وب (در حال توسعه روی لوکال) به API
# در Production حتماً این لیست را محدود به دامنه واقعی پنل کنید
# ===========================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # بدون این خط، مرورگر هدر شمارش کل را به فرانت‌اند نمی‌دهد و
    # صفحه‌بندی «بارگذاری بیشتر» هرگز کار نمی‌کند.
    expose_headers=["X-Total-Count", "ETag"],
)

# پاسخ ۳۰۴ برای درخواست‌های GET بدون تغییر (به‌ویژه روی موبایل)
app.add_middleware(ETagMiddleware)


# ===========================================================
# هدرهای امنیتی پایه برای همه‌ی پاسخ‌ها
# پیش از این هیچ‌کدام تنظیم نمی‌شد؛ به‌ویژه دانلود پیوست‌ها بدون
# nosniff بود و مرورگر می‌توانست محتوای یک فایل «.txt» را HTML تفسیر کند.
# ===========================================================
@app.middleware("http")
async def _security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Cache-Control", "no-store")
    return response


# ===========================================================
# هندلرهای خطای سراسری دیتابیس
# پیش از این، داده‌ی نامعتبر کلاینت (مثلاً رشته‌ی بلندتر از ستون)
# به خطای ۵۰۰ با stack trace کامل در لاگ تبدیل می‌شد. حالا:
#   * DataError (مثل StringDataRightTruncation) -> 400
#   * IntegrityError (مثل نقض یکتایی در race) -> 409
# جزئیات کامل فقط سمت سرور لاگ می‌شود، نه در پاسخ کلاینت.
# ===========================================================
@app.exception_handler(DataError)
async def _data_error_handler(request: Request, exc: DataError):
    app_logger.error(f"DataError on {request.method} {request.url.path}: {exc}")
    return JSONResponse(status_code=400, content={"detail": "داده‌ی ارسالی معتبر نیست."})


@app.exception_handler(IntegrityError)
async def _integrity_error_handler(request: Request, exc: IntegrityError):
    app_logger.error(f"IntegrityError on {request.method} {request.url.path}: {exc}")
    return JSONResponse(status_code=409, content={"detail": "رکورد تکراری یا نامعتبر است."})

# ===========================================================
# ثبت Router ها
# ===========================================================
app.include_router(auth_router)
app.include_router(leads_router)
app.include_router(tasks_router)
app.include_router(public_users_router)
app.include_router(users_router)
app.include_router(dashboard_router)
app.include_router(notifications_router)
app.include_router(audit_logs_router)
app.include_router(deleted_leads_router)
app.include_router(admin_lead_history_router)
app.include_router(products_router)

# پوشه‌ی آپلود باید صریحاً ساخته شود؛ پیش از این فقط به این دلیل کار
# می‌کرد که routes/leads.py هنگام import آن را می‌ساخت — یعنی صرفاً
# جابه‌جایی ترتیب import‌ها باعث کرش در استارتاپ می‌شد.
os.makedirs("uploads/leads", exist_ok=True)

# SECURITY: the previous `app.mount("/uploads", StaticFiles(...))` served
# every uploaded customer document WITHOUT authentication. Attachments are
# now streamed only through the authorized endpoint:
#   GET /leads/{lead_id}/attachments/{attachment_id}/download


# ===========================================================
# اولین API پروژه
# فقط برای تست بالا آمدن پروژه است.
# ===========================================================
@app.get("/")
def home():
    """بررسی سالم بودن پروژه"""
    app_logger.info("Home endpoint called")
    return {
        "project": settings.PROJECT_NAME,
        "status": "Running",
        "version": settings.VERSION,
    }


# ===========================================================
# زمان‌بند در lifespan (بالای همین فایل) روشن می‌شود.
#
# توجه برای استقرار چندنسخه‌ای: lifespan در *هر* فرایند worker
# اجرا می‌شود؛ بنابراین با uvicorn --workers N یا چند کانتینر،
# باید روی همه‌ی نمونه‌ها به‌جز یکی ENABLE_SCHEDULER=false تنظیم
# شود، وگرنه jobها N بار اجرا و اعلان‌ها تکرار می‌شوند.
# ===========================================================
