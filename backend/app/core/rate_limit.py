"""
===========================================================
محدودسازی نرخ ورود (brute-force / credential-stuffing control)
-----------------------------------------------------------
پیش از این /auth/login هیچ throttle‌ای نداشت: حدس رمز نامحدود بود و
Argon2 فقط هزینه‌ی هر تلاش را بالا می‌برد، نه تعدادشان را.

مدل فعلی — sliding window در حافظه‌ی فرایند:
  * به ازای هر (IP + شماره‌ی نرمال‌شده): حداکثر
    LOGIN_MAX_FAILURES_PER_ACCOUNT ورودِ ناموفق در پنجره‌ی
    LOGIN_RATE_WINDOW_SECONDS → بعد از آن 429 با Retry-After.
  * به ازای هر IP (فارغ از شماره): حداکثر LOGIN_MAX_FAILURES_PER_IP
    ورود ناموفق در همان پنجره — برای بستن مسیرِ «یک بار مصرف برای
    هر شماره» در credential stuffing.
  * ورود موفق، شمارنده‌ی همان (IP+شماره) را صفر می‌کند؛ بودجه‌ی IP
    عمداً صفر نمی‌شود تا مهاجم نتواند با یک حساب معتبر، بودجه‌ی
    حدس‌زدنِ بقیه‌ی شماره‌ها را بازیابی کند.

محدودیت معماری (مستند و عمدی): این limiter در حافظه‌ی هر فرایند است.
با uvicorn --workers N یا چند کانتینر، هر replica بودجه‌ی مستقل دارد
(یعنی مؤثر N برابر). برای استقرار چندنسخه‌ای باید throttle مشترک
(Redis/درگاه API) جلوی سرویس گذاشته شود؛ این لایه حداقلِ دفاعِ
داخل برنامه است، نه جایگزینِ edge limiting.
===========================================================
"""
import threading
import time

from fastapi import HTTPException, Request, status

from app.config.settings import settings
from app.core.text_normalization import normalize_mobile


class SlidingWindowCounter:
    """شمارنده‌ی پنجره‌ی لغزنده، thread-safe و بدون وابستگی خارجی."""

    def __init__(self, max_events: int, window_seconds: int):
        self.max_events = max_events
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> list[float]:
        cutoff = now - self.window_seconds
        hits = [t for t in self._hits.get(key, ()) if t > cutoff]
        if hits:
            self._hits[key] = hits
        else:
            self._hits.pop(key, None)
        return hits

    def check(self, key: str) -> tuple[bool, int]:
        """بدون ثبت رویداد: (allowed, retry_after_seconds)."""
        now = time.monotonic()
        with self._lock:
            hits = self._prune(key, now)
            if len(hits) >= self.max_events:
                retry_after = int(self.window_seconds - (now - hits[0])) + 1
                return False, max(retry_after, 1)
            return True, 0

    def record(self, key: str) -> tuple[bool, int]:
        """ثبت یک رویداد و بررسی عبور از حد مجاز."""
        now = time.monotonic()
        with self._lock:
            hits = self._prune(key, now)
            hits.append(now)
            self._hits[key] = hits
            if len(hits) > self.max_events:
                retry_after = int(self.window_seconds - (now - hits[0])) + 1
                return False, max(retry_after, 1)
            return True, 0

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()


# نمونه‌های سراسری (یک‌بار در فرایند ساخته می‌شوند)
_FAILURE_PER_ACCOUNT = SlidingWindowCounter(
    max_events=settings.LOGIN_MAX_FAILURES_PER_ACCOUNT,
    window_seconds=settings.LOGIN_RATE_WINDOW_SECONDS,
)
_FAILURE_PER_IP = SlidingWindowCounter(
    max_events=settings.LOGIN_MAX_FAILURES_PER_IP,
    window_seconds=settings.LOGIN_RATE_WINDOW_SECONDS,
)

_TOO_MANY_REQUESTS_DETAIL = (
    "تلاش‌های ناموفق بیش از حد مجاز؛ لطفاً کمی بعد دوباره تلاش کنید."
)


def _client_ip(request: Request) -> str:
    """IP کلاینت؛ پشت reverse proxy به اولین مقدار X-Forwarded-For اعتماد می‌شود."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _identity_key(username: str | None) -> str:
    """کلید هویت: شماره‌ی نرمال‌شده تا «۰۹۱۲…» و «+۹۸۹۱۲…» یک کلید باشند."""
    normalized = normalize_mobile(username) if username else None
    return normalized or (username or "").strip().lower()


def clear_login_counters() -> None:
    """فقط برای تست‌ها: پاک‌سازی کامل شمارنده‌ها."""
    _FAILURE_PER_ACCOUNT.clear()
    _FAILURE_PER_IP.clear()


def login_rate_guard(request: Request, username: str | None) -> None:
    """پیش از پردازش لاگین: اگر بودجه تمام شده، 429 برگردان."""
    ip = _client_ip(request)

    allowed, retry_after = _FAILURE_PER_IP.check(f"ip:{ip}")
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=_TOO_MANY_REQUESTS_DETAIL,
            headers={"Retry-After": str(retry_after)},
        )

    allowed, retry_after = _FAILURE_PER_ACCOUNT.check(f"acct:{ip}|{_identity_key(username)}")
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=_TOO_MANY_REQUESTS_DETAIL,
            headers={"Retry-After": str(retry_after)},
        )


def report_login_failure(request: Request, username: str | None) -> None:
    """ثبت یک تلاش ناموفق در هر دو شمارنده."""
    ip = _client_ip(request)
    _FAILURE_PER_IP.record(f"ip:{ip}")
    _FAILURE_PER_ACCOUNT.record(f"acct:{ip}|{_identity_key(username)}")


def report_login_success(request: Request, username: str | None) -> None:
    """ورود موفق: بودجه‌ی همان (IP+شماره) بازمی‌گردد؛ بودجه‌ی IP نه."""
    _FAILURE_PER_ACCOUNT.reset(f"acct:{_client_ip(request)}|{_identity_key(username)}")
