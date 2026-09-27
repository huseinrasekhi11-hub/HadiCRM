"""
===========================================================
محدودسازی نرخ ورود (brute-force / credential-stuffing control)
-----------------------------------------------------------
پیش از این /auth/login هیچ throttle‌ای نداشت: حدس رمز نامحدود بود و
Argon2 فقط هزینه‌ی هر تلاش را بالا می‌برد، نه تعدادشان را.

مدل فعلی — پنجره‌ی لغزنده روی یک انبارِ «مشترک»:
  * به ازای هر (IP + شماره‌ی نرمال‌شده): حداکثر
    LOGIN_MAX_FAILURES_PER_ACCOUNT ورودِ ناموفق در پنجره‌ی
    LOGIN_RATE_WINDOW_SECONDS → بعد از آن 429 با Retry-After.
  * به ازای هر IP (فارغ از شماره): حداکثر LOGIN_MAX_FAILURES_PER_IP
    ورود ناموفق در همان پنجره — برای بستن مسیرِ «یک بار مصرف برای
    هر شماره» در credential stuffing.
  * ورود موفق، شمارنده‌ی همان (IP+شماره) را صفر می‌کند؛ بودجه‌ی IP
    عمداً صفر نمی‌شود تا مهاجم نتواند با یک حساب معتبر، بودجه‌ی
    حدس‌زدنِ بقیه‌ی شماره‌ها را بازیابی کند.

دو انبار وجود دارد (انتخاب با LOGIN_RATE_BACKEND):

  * "db"     → DatabaseRateLimiter: شمارنده‌ها در جدول login_rate_events
               (مهاجرت e3f1c9b7d4a2) و بین همه‌ی workerها/replicaها مشترک.
               این حالتِ پیش‌فرض است ("auto") چون دیتابیس از قبل بین همه‌ی
               نمونه‌ها مشترک است و وابستگیِ تازه‌ای (Redis و ...) نمی‌خواهد.
  * "memory" → SlidingWindowCounter در حافظه‌ی فرایند (سریع، ولی هر
               replica بودجه‌ی مستقل دارد؛ فقط برای توسعه/تست یا وقتی
               throttle در لبه (gateway/WAF/CDN) انجام می‌شود).

در حالت "auto" شمارنده‌ی حافظه‌ای هم به‌عنوانِ خطِ اولِ ارزان نگه داشته
می‌شود (وقتی یک کلاینت از قبل در همین فرایند مسدود شده، رفت‌وبرگشتِ
دیتابیس حذف می‌شود)، اما تصمیمِ نهایی با انبارِ مشترک است: سقفِ مؤثر
همان LOGIN_MAX_FAILURES_* است، نه N برابرِ تعداد نمونه‌ها.

نکته برای استقرارهای خیلی پردازش‌سنگین: هنوز توصیه می‌شود throttle اصلی
در لبه/درگاه (و یا Redis در صورتِ موجودبودن) هم انجام شود؛ این لایه
دفاعِ داخل برنامه است، نه جایگزینِ edge limiting.
===========================================================
"""
import threading
import time
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, status
from sqlalchemy.exc import SQLAlchemyError

from app.config.settings import settings
from app.core.logger import app_logger
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


class DatabaseRateLimiter:
    """
    شمارنده‌ی پنجره‌ی لغزنده روی دیتابیسِ مشترک.

    هر تلاشِ ناموفق یک ردیف در login_rate_events می‌گذارد؛ شمارش و
    پاک‌سازی همیشه در یک تراکنشِ کوتاه و مستقل انجام می‌شود (نه روی
    session درخواست) تا ابطال یا خطای دیتابیس در خودِ لاگین، بودجه‌ی
    محدودسازی را پاک نکند و برعکس، شمارش‌ها بین workerها دیده شوند.
    """

    # هر چند تماس یک‌بار، ردیف‌های قدیمیِ «همه‌ی کلیدها» پاک می‌شوند؛
    # پاک‌سازیِ per-key در هر record انجام می‌شود و این فقط برای کلیدهای
    # رهاشده است (مثلاً IPهایی که دیگر هرگز تلاش نمی‌کنند).
    _GLOBAL_PRUNE_EVERY = 25

    def __init__(self, session_factory, max_events: int, window_seconds: int):
        self._session_factory = session_factory
        self.max_events = max_events
        self.window_seconds = window_seconds
        self._calls = 0
        self._lock = threading.Lock()

    # -- internals -------------------------------------------------
    def _new_session(self):
        # ایمپورتِ محلی: جلوگیری از چرخه‌ی import در زمانِ راه‌اندازی
        from app.database.database import SessionLocal

        return (self._session_factory or SessionLocal)()

    def _count(self, db, key: str, cutoff: datetime) -> tuple[int, datetime | None]:
        from sqlalchemy import func

        from app.models.login_rate_event import LoginRateEvent

        row = (
            db.query(
                func.count(LoginRateEvent.id),
                func.min(LoginRateEvent.created_at),
            )
            .filter(
                LoginRateEvent.event_key == key,
                LoginRateEvent.created_at > cutoff,
            )
            .one()
        )
        return int(row[0] or 0), row[1]

    def _prune_key(self, db, key: str, cutoff: datetime) -> None:
        from app.models.login_rate_event import LoginRateEvent

        db.query(LoginRateEvent).filter(
            LoginRateEvent.event_key == key,
            LoginRateEvent.created_at <= cutoff,
        ).delete(synchronize_session=False)

    def _prune_all(self, db, cutoff: datetime) -> None:
        from app.models.login_rate_event import LoginRateEvent

        db.query(LoginRateEvent).filter(
            LoginRateEvent.created_at <= cutoff
        ).delete(synchronize_session=False)

    def _retry_after(self, oldest: datetime | None, now: datetime) -> int:
        if oldest is None:
            return 1
        if oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=timezone.utc)
        retry_after = int((oldest + timedelta(seconds=self.window_seconds) - now).total_seconds()) + 1
        return max(retry_after, 1)

    # -- public API (هم‌امضا با SlidingWindowCounter) ---------------
    def check(self, key: str) -> tuple[bool, int]:
        """بدون ثبت رویداد: (allowed, retry_after_seconds)."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=self.window_seconds)
        db = self._new_session()
        try:
            count, oldest = self._count(db, key, cutoff)
        except SQLAlchemyError as exc:
            app_logger.warning(f"[RateLimit] shared counter check failed ({exc})")
            return True, 0  # دیتابیسِ پایین‌دست؛ لاگین خودش هم شکست می‌خورد
        finally:
            db.close()

        if count >= self.max_events:
            return False, self._retry_after(oldest, now)
        return True, 0

    def record(self, key: str) -> tuple[bool, int]:
        """ثبت یک تلاش ناموفق و بررسی عبور از حد مجاز."""
        from app.models.login_rate_event import LoginRateEvent

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=self.window_seconds)

        with self._lock:
            self._calls += 1
            do_global_prune = self._calls % self._GLOBAL_PRUNE_EVERY == 0

        db = self._new_session()
        try:
            self._prune_key(db, key, cutoff)
            if do_global_prune:
                self._prune_all(db, cutoff)
            db.add(LoginRateEvent(event_key=key, created_at=now))
            db.flush()
            count, oldest = self._count(db, key, cutoff)
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            app_logger.warning(f"[RateLimit] shared counter record failed ({exc})")
            return True, 0
        finally:
            db.close()

        if count > self.max_events:
            return False, self._retry_after(oldest, now)
        return True, 0

    def prune_expired(self) -> int:
        """حذفِ همه‌ی رویدادهای خارج از پنجره (job نگهداری)."""
        from app.models.login_rate_event import LoginRateEvent

        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self.window_seconds)
        db = self._new_session()
        try:
            removed = (
                db.query(LoginRateEvent)
                .filter(LoginRateEvent.created_at <= cutoff)
                .delete(synchronize_session=False)
            )
            db.commit()
            return int(removed)
        except SQLAlchemyError as exc:
            db.rollback()
            app_logger.warning(f"[RateLimit] shared counter prune failed ({exc})")
            return 0
        finally:
            db.close()

    def reset(self, key: str) -> None:
        from app.models.login_rate_event import LoginRateEvent

        db = self._new_session()
        try:
            db.query(LoginRateEvent).filter(
                LoginRateEvent.event_key == key
            ).delete(synchronize_session=False)
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            app_logger.warning(f"[RateLimit] shared counter reset failed ({exc})")
        finally:
            db.close()

    def clear(self) -> None:
        """فقط برای تست‌ها: حذفِ کاملِ شمارنده‌های مشترک."""
        from app.models.login_rate_event import LoginRateEvent

        db = self._new_session()
        try:
            db.query(LoginRateEvent).delete(synchronize_session=False)
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            app_logger.warning(f"[RateLimit] shared counter clear failed ({exc})")
        finally:
            db.close()


def _build_shared_counters():
    """
    ساخت شمارنده‌های مشترک طبق تنظیمات.

    "memory" → فقط حافظه (بودجه‌ی مستقل برای هر فرایند)
    "db"     → فقط دیتابیس
    "auto"   → دیتابیس (مشترک) + حافظه به‌عنوان میانبرِ ارزان (پیش‌فرض)
    """
    backend = (settings.LOGIN_RATE_BACKEND or "auto").strip().lower()

    memory_account = SlidingWindowCounter(
        max_events=settings.LOGIN_MAX_FAILURES_PER_ACCOUNT,
        window_seconds=settings.LOGIN_RATE_WINDOW_SECONDS,
    )
    memory_ip = SlidingWindowCounter(
        max_events=settings.LOGIN_MAX_FAILURES_PER_IP,
        window_seconds=settings.LOGIN_RATE_WINDOW_SECONDS,
    )

    shared_account = None
    shared_ip = None
    if backend in ("auto", "db", "database", "shared"):
        shared_account = DatabaseRateLimiter(
            session_factory=None,
            max_events=settings.LOGIN_MAX_FAILURES_PER_ACCOUNT,
            window_seconds=settings.LOGIN_RATE_WINDOW_SECONDS,
        )
        shared_ip = DatabaseRateLimiter(
            session_factory=None,
            max_events=settings.LOGIN_MAX_FAILURES_PER_IP,
            window_seconds=settings.LOGIN_RATE_WINDOW_SECONDS,
        )
    elif backend not in ("memory", "inmemory", "in-memory", "local"):
        app_logger.warning(
            f"[RateLimit] unknown LOGIN_RATE_BACKEND={backend!r}; "
            "falling back to the shared database backend."
        )
        shared_account = DatabaseRateLimiter(
            session_factory=None,
            max_events=settings.LOGIN_MAX_FAILURES_PER_ACCOUNT,
            window_seconds=settings.LOGIN_RATE_WINDOW_SECONDS,
        )
        shared_ip = DatabaseRateLimiter(
            session_factory=None,
            max_events=settings.LOGIN_MAX_FAILURES_PER_IP,
            window_seconds=settings.LOGIN_RATE_WINDOW_SECONDS,
        )

    return {
        "memory_account": memory_account,
        "memory_ip": memory_ip,
        "shared_account": shared_account,
        "shared_ip": shared_ip,
    }


_COUNTERS = _build_shared_counters()

_FAILURE_PER_ACCOUNT = _COUNTERS["memory_account"]
_FAILURE_PER_IP = _COUNTERS["memory_ip"]
_SHARED_PER_ACCOUNT = _COUNTERS["shared_account"]
_SHARED_PER_IP = _COUNTERS["shared_ip"]

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
    """فقط برای تست‌ها: پاک‌سازی کامل شمارنده‌ها (حافظه و دیتابیس)."""
    _FAILURE_PER_ACCOUNT.clear()
    _FAILURE_PER_IP.clear()
    if _SHARED_PER_ACCOUNT is not None:
        _SHARED_PER_ACCOUNT.clear()
    if _SHARED_PER_IP is not None:
        _SHARED_PER_IP.clear()


def login_rate_guard(request: Request, username: str | None) -> None:
    """پیش از پردازش لاگین: اگر بودجه تمام شده، 429 برگردان."""
    ip = _client_ip(request)
    ip_key = f"ip:{ip}"
    account_key = f"acct:{ip}|{_identity_key(username)}"

    # ۱) میانبرِ ارزانِ داخل فرایند (بدون رفت‌وبرگشتِ دیتابیس)
    allowed, retry_after = _FAILURE_PER_IP.check(ip_key)
    if not allowed:
        raise _too_many_requests(retry_after)

    allowed, retry_after = _FAILURE_PER_ACCOUNT.check(account_key)
    if not allowed:
        raise _too_many_requests(retry_after)

    # ۲) تصمیمِ نهایی با انبارِ مشترک: بودجه در همه‌ی workerها/replicaها
    #    یکی است، نه به تعدادِ فرایندها ضرب‌شده.
    if _SHARED_PER_IP is not None:
        allowed, retry_after = _SHARED_PER_IP.check(ip_key)
        if not allowed:
            raise _too_many_requests(retry_after)

    if _SHARED_PER_ACCOUNT is not None:
        allowed, retry_after = _SHARED_PER_ACCOUNT.check(account_key)
        if not allowed:
            raise _too_many_requests(retry_after)


def report_login_failure(request: Request, username: str | None) -> None:
    """ثبت یک تلاش ناموفق در شمارنده‌های حافظه‌ای و مشترک."""
    ip = _client_ip(request)
    ip_key = f"ip:{ip}"
    account_key = f"acct:{ip}|{_identity_key(username)}"

    _FAILURE_PER_IP.record(ip_key)
    _FAILURE_PER_ACCOUNT.record(account_key)

    if _SHARED_PER_IP is not None:
        _SHARED_PER_IP.record(ip_key)
    if _SHARED_PER_ACCOUNT is not None:
        _SHARED_PER_ACCOUNT.record(account_key)


def report_login_success(request: Request, username: str | None) -> None:
    """ورود موفق: بودجه‌ی همان (IP+شماره) بازمی‌گردد؛ بودجه‌ی IP نه."""
    account_key = f"acct:{_client_ip(request)}|{_identity_key(username)}"

    _FAILURE_PER_ACCOUNT.reset(account_key)
    if _SHARED_PER_ACCOUNT is not None:
        _SHARED_PER_ACCOUNT.reset(account_key)


def cleanup_login_rate_events(retention_seconds: int | None = None) -> int:
    """
    نگهداری: حذفِ رویدادهای محدودسازِ خارج از پنجره تا جدولِ
    login_rate_events روی استقرارهای کم‌ترافیک هم رشد بی‌پایان نکند.
    (فراخوانی از job زمان‌بند — app/scheduler/jobs.py)
    """
    window = retention_seconds or settings.LOGIN_RATE_WINDOW_SECONDS
    limiter = DatabaseRateLimiter(
        session_factory=None, max_events=1, window_seconds=window
    )
    removed = limiter.prune_expired()
    if removed:
        app_logger.info(f"[RateLimit] pruned {removed} expired login-rate event(s).")
    return removed


def _too_many_requests(retry_after: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=_TOO_MANY_REQUESTS_DETAIL,
        headers={"Retry-After": str(retry_after)},
    )
