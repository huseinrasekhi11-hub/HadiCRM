"""
===========================================================
محافظتِ CSRF برای اندپوینت‌های مبتنی بر کوکی
-----------------------------------------------------------
وقتی توکن تمدید در کوکیِ HttpOnly است، هر سایتِ دیگری می‌تواند یک فرم/فچِ
بین‌سایتی به /auth/refresh-token یا /auth/logout بفرستد و مرورگر کوکی را
همراه آن بفرستد. دیتا دزدیده نمی‌شود (پاسخ بین‌دامنه‌ای قابل خواندن نیست)
اما مهاجم می‌تواند نشستِ قربانی را بچرخاند/خارج کند.

دفاع: برای درخواست‌هایی که احراز هویت‌شان از کوکی آمده، هدرِ Origin باید
با یکی از دامنه‌های مجازِ CORS یکی باشد. مرورگرها در همه‌ی درخواست‌های
POSTِ بین‌دامنه‌ای Origin می‌فرستند، بنابراین این بررسی حمله را بلاک
می‌کند؛ کلاینت‌هایی که Origin نمی‌فرستند (curl، اپ موبایل) تحت‌تأثیر
قرار نمی‌گیرند چون کوکیِ مرورگر را ندارند.
===========================================================
"""
from fastapi import HTTPException, Request, status

from app.config.settings import settings


def _allowed_origins() -> set[str]:
    return {origin.strip().lower().rstrip("/") for origin in settings.cors_origin_list}


def enforce_csrf_for_cookie_auth(request: Request) -> None:
    """
    فقط زمانی اعمال می‌شود که هویت از کوکی آمده باشد (یعنی کلاینت هیچ
    توکنی در بدنه نفرستاده). اگر Origin ناشناس باشد → ۴۰۱ عمومی.
    """
    origin = request.headers.get("origin")
    if not origin:
        # کلاینت‌های غیرمرورگری / هم‌دامنه‌ایِ قدیمی؛ چیزی برای جعل ندارند
        return

    allowed = _allowed_origins()
    if origin.lower().rstrip("/") in allowed:
        return

    if allowed == {"*"}:
        # پیکربندیِ wildcard با credentials معتبر نیست؛ اینجا محافظه‌کارانه
        # رد می‌کنیم تا نشتِ پیکربندی به یک حفره‌ی CSRF تبدیل نشود.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="توکن تمدید نامعتبر یا منقضی شده است",
            headers={"WWW-Authenticate": "Bearer"},
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="توکن تمدید نامعتبر یا منقضی شده است",
        headers={"WWW-Authenticate": "Bearer"},
    )
