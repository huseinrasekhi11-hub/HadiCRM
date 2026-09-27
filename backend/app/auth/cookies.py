"""
===========================================================
کوکیِ HttpOnly برای توکن تمدید (رفعِ نگهداریِ توکن در localStorage)
-----------------------------------------------------------
چرا؟ توکن‌ها در localStorage برای *هر* اسکریپتی که روی صفحه اجرا شود
قابل خواندن‌اند؛ یعنی یک XSSِ کوچک (کتابخانه‌ی آلوده، محتوایِ کاربرِ
ذخیره‌شده، ...) مساوی است با دزدیده‌شدنِ نشستِ کاربر. کوکیِ HttpOnly
از دسترسِ document.cookie خارج است.

طرح:
  * توکن تمدید (refresh) → کوکیِ HttpOnly با SameSite/Secureِ قابل‌تنظیم،
    و فقط برای مسیرهای /auth ارسال می‌شود (کمترین سطحِ در معرض بودن).
  * توکن دسترسی (access) → بدنه‌ی پاسخ و نگهداری در حافظه‌ی فرانت‌اند
    (نه localStorage)؛ با هر بار رفرش/بارگذاریِ صفحه از طریقِ کوکیِ
    تمدید دوباره صادر می‌شود.
  * سازگاری: اگر کلاینتی (مثل اپ موبایل یا کلاینتِ قدیمی) توکن را در
    بدنه بفرستد، همان مسیر قبلی هم کار می‌کند.

توجه: در استقرارِ چنددامنه‌ای (فرانت‌اند و API روی دامنه‌های متفاوت)
SameSite=None لازم است و برخی مرورگرها (به‌ویژه Safari) کوکی‌های
بین‌سایتی را مسدود می‌کنند. راهِ پایدار، سرو‌کردنِ فرانت‌اند و API روی
یک دامنه (reverse proxy / rewrite) است — در آن صورت
REFRESH_COOKIE_SAMESITE=lax تنظیم شود.
===========================================================
"""
from fastapi import Request, Response

from app.config.settings import settings


def cookie_path(request: Request | None = None) -> str:
    """
    مسیرِ کوکی.

    وقتی API پشت یک پیشوند (مثل /api) سرو می‌شود، مسیرِ کوکی هم باید همان
    پیشوند را داشته باشد — وگرنه مرورگر کوکیِ `Path=/auth` را برای
    درخواستِ `/api/auth/refresh-token` نمی‌فرستد و نشست بعد از هر
    بارگذاریِ صفحه می‌پرد. در آن استقرارها یا `REFRESH_COOKIE_PATH` را
    صریحاً تنظیم کنید (مثلاً `/api/auth`)، یا `root_path` را در اختیارِ
    برنامه بگذارید (uvicorn --root-path / --proxy-headers).
    """
    root_path = ""
    if request is not None:
        root_path = (request.scope.get("root_path") or "").rstrip("/")
    return f"{root_path}{settings.REFRESH_COOKIE_PATH}"


def set_refresh_cookie(response: Response, token: str, request: Request | None = None) -> None:
    """نصبِ کوکیِ توکن تمدید روی پاسخ."""
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        expires=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path=cookie_path(request),
        domain=settings.REFRESH_COOKIE_DOMAIN,
        secure=settings.REFRESH_COOKIE_SECURE,
        httponly=True,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
    )


def clear_refresh_cookie(response: Response, request: Request | None = None) -> None:
    """حذفِ کوکیِ توکن تمدید (logout / انقضا / خطا)."""
    response.delete_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        path=cookie_path(request),
        domain=settings.REFRESH_COOKIE_DOMAIN,
        secure=settings.REFRESH_COOKIE_SECURE,
        httponly=True,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
    )
