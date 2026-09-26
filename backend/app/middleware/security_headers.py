"""
Basic browser security headers for every API response.

پیش از این هیچ‌کدام از این هدرها تنظیم نمی‌شد:
  * X-Content-Type-Options: nosniff — به‌ویژه برای دانلود پیوست‌ها؛
    بدون آن مرورگر می‌توانست محتوای یک فایل «.txt» را HTML تفسیر کند.
  * X-Frame-Options: DENY — جلوگیری از clickjacking (قرار گرفتن API/پنل
    داخل iframe یک سایت متخاصم).
  * Referrer-Policy: no-referrer — مسیرهای API (که می‌توانند شناسه‌ی
    رکوردها را در URL داشته باشند) به‌عنوان Referrer به دامنه‌های
    دیگر نشت نکنند.
  * Cache-Control: no-store — پاسخ‌های دارای توکن/داده‌ی CRM در حافظه‌ی
    نهانِ مرورگر یا پروکسی‌های اشتراکی باقی نمانند.

این هدرها «hardening کم‌ریسک» هستند: هیچ‌کدام جریان عادی برنامه را
تغییر نمی‌دهند و با setDefault افزوده می‌شوند تا هدرهای صریحِ لایه‌های
دیگر (در صورت وجود) بازنویسی نشوند.
"""
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        for name, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response
