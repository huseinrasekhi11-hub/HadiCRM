"""
===========================================================
محدودسازی نرخِ عملیاتِ حساسی که با حدس‌زدن قابل حمله‌اند
(ورود = brute-force / credential-stuffing، و تغییر رمز)
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
  * همین مدل برای «تغییر رمزِ عبور» هم اعمال می‌شود (حدسِ رمزِ فعلی
    روی یک نشستِ لاگین‌شده هم باید محدود باشد).

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
    def __init__(self, session_factory, max_events: int, window_seconds: int):
        self._session_factory = session_factory
        self.max_events = max_events
        self.window_seconds = window_seconds

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

    def _lock_key(self, db, key: str) -> None:
        """Serialize count+insert/reset for the same bucket on PostgreSQL."""
        if db.get_bind().dialect.name == "postgresql":
            db.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": key},
            )

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
            app_logger.exception(f"[RateLimit] shared counter check failed ({exc})")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Login protection is temporarily unavailable.",
            ) from exc
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

        db = self._new_session()
        try:
            # Serialize each bucket in PostgreSQL so concurrent workers cannot
            # all observe the same pre-insert count and exceed the budget.
            self._lock_key(db, key)
            self._prune_key(db, key, cutoff)
            count, oldest = self._count(db, key, cutoff)
            if count >= self.max_events:
                db.rollback()
                return False, self._retry_after(oldest, now)

            db.add(LoginRateEvent(event_key=key, created_at=now))
            db.flush()
            count, oldest = self._count(db, key, cutoff)
            if count > self.max_events:
                db.rollback()
                return False, self._retry_after(oldest, now)

            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            app_logger.exception(f"[RateLimit] shared counter record failed ({exc})")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Login protection is temporarily unavailable.",
            ) from exc
        finally:
            db.close()

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


class RateBudget:
    """
    یک بودجه‌ی نام‌دار (مثلاً «ورودِ ناموفق برای این شماره») که تصمیم را
    ابتدا با شمارنده‌ی ارزانِ داخل فرایند و سپس با انبارِ مشترک می‌گیرد.

    نکته‌ی مهم: انبارِ مشترک «مرجع» است. اگر مقدارِ
    LOGIN_RATE_BACKEND=memory تنظیم شود، فقط حافظه استفاده می‌شود و سقفِ
    مؤثر به تعداد فرایندها ضرب خواهد شد (برای توسعه/تست یا وقتی throttle
    در لبه انجام می‌شود).
    """

    def __init__(self, name: str, max_events: int, window_seconds: int, use_shared: bool):
        self.name = name
        self.max_events = max_events
        self.window_seconds = window_seconds
        self._memory = SlidingWindowCounter(max_events, window_seconds)
        self._shared = (
            DatabaseRateLimiter(
                session_factory=None,
                max_events=max_events,
                window_seconds=window_seconds,
            )
            if use_shared
            else None
        )

    # -- introspection (تست‌ها) -------------------------------------
    @property
    def shared(self) -> DatabaseRateLimiter | None:
        return self._shared

    @property
    def memory(self) -> SlidingWindowCounter:
        return self._memory

    def clear_memory_only(self) -> None:
        """پاک‌سازیِ فقط شمارنده‌ی حافظه‌ای (شبیه‌سازیِ یک فرایندِ تازه)."""
        self._memory.clear()

    # -- operations -------------------------------------------------
    def check(self, key: str) -> tuple[bool, int]:
        if self._shared is not None:
            return self._shared.check(key)
        return self._memory.check(key)

    def record(self, key: str) -> tuple[bool, int]:
        if self._shared is not None:
            return self._shared.record(key)
        return self._memory.record(key)

    def reset(self, key: str) -> None:
        self._memory.reset(key)
        if self._shared is not None:
            self._shared.reset(key)

    def clear(self) -> None:
        self._memory.clear()
        if self._shared is not None:
            self._shared.clear()


def _use_shared_backend() -> bool:
    backend = (settings.LOGIN_RATE_BACKEND or "auto").strip().lower()
    if backend in ("memory", "inmemory", "in-memory", "local", "off", "none"):
        return False
    if backend in ("auto", "db", "database", "shared"):
        return True
    app_logger.warning(
        f"[RateLimit] unknown LOGIN_RATE_BACKEND={backend!r}; "
        "using the shared database backend."
    )
    return True


_USE_SHARED = _use_shared_backend()
_WINDOW = settings.LOGIN_RATE_WINDOW_SECONDS

# بودجه‌ی ورود: (IP + شماره) و (IP)
_LOGIN_ACCOUNT = RateBudget(
    "login-account", settings.LOGIN_MAX_FAILURES_PER_ACCOUNT, _WINDOW, _USE_SHARED
)
_LOGIN_IP = RateBudget(
    "login-ip", settings.LOGIN_MAX_FAILURES_PER_IP, _WINDOW, _USE_SHARED
)

# بودجه‌ی تغییر رمز: حدسِ «رمز فعلی» روی نشستِ لاگین‌شده هم باید محدود باشد
_PASSWORD_ACCOUNT = RateBudget(
    "password-change",
    settings.PASSWORD_CHANGE_MAX_FAILURES,
    settings.PASSWORD_CHANGE_WINDOW_SECONDS,
    _USE_SHARED,
)

_TOO_MANY_REQUESTS_DETAIL = (
    "تلاش‌های ناموفق بیش از حد مجاز؛ لطفاً کمی بعد دوباره تلاش کنید."
)


def _trusted_proxy_networks():
    networks = []
    for raw in settings.TRUSTED_PROXY_IPS.split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            networks.append(ipaddress.ip_network(raw, strict=False))
        except ValueError:
            app_logger.warning(f"[RateLimit] invalid TRUSTED_PROXY_IPS entry ignored: {raw!r}")
    return networks


def _client_ip(request: Request) -> str:
    """
    Trust X-Forwarded-For only when the immediate peer is explicitly trusted.
    Walk right-to-left so a client cannot prepend a forged address to evade
    the per-IP brute-force budget.
    """
    peer = request.client.host if request.client else "unknown"
    try:
        peer_ip = ipaddress.ip_address(peer)
    except ValueError:
        peer_ip = None

    networks = _trusted_proxy_networks()
    if peer_ip is None or not any(peer_ip in network for network in networks):
        return peer

    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded:
        return peer

    for candidate in reversed([part.strip() for part in forwarded.split(",")]):
        try:
            candidate_ip = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if not any(candidate_ip in network for network in networks):
            return str(candidate_ip)

    return peer


def _identity_key(username: str | None) -> str:
    """کلید هویت: شماره‌ی نرمال‌شده تا «۰۹۱۲…» و «+۹۸۹۱۲…» یک کلید باشند."""
    normalized = normalize_mobile(username) if username else None
    return normalized or (username or "").strip().lower()


def _too_many_requests(retry_after: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=_TOO_MANY_REQUESTS_DETAIL,
        headers={"Retry-After": str(retry_after)},
    )


# -----------------------------------------------------------
# ورود (login)
# -----------------------------------------------------------
def clear_login_counters() -> None:
    """فقط برای تست‌ها: پاک‌سازی کامل شمارنده‌ها (حافظه و دیتابیس)."""
    _LOGIN_ACCOUNT.clear()
    _LOGIN_IP.clear()


def login_rate_guard(request: Request, username: str | None) -> None:
    """پیش از پردازش لاگین: اگر بودجه تمام شده، 429 برگردان."""
    ip = _client_ip(request)

    # ۱) بودجه‌ی IP (ضدِ credential stuffing روی شماره‌های مختلف)
    allowed, retry_after = _LOGIN_IP.check(f"ip:{ip}")
    if not allowed:
        raise _too_many_requests(retry_after)

    # ۲) بودجه‌ی (IP + حساب) — تصمیم نهایی با انبارِ مشترک است
    allowed, retry_after = _LOGIN_ACCOUNT.check(
        f"acct:{ip}|{_identity_key(username)}"
    )
    if not allowed:
        raise _too_many_requests(retry_after)


def report_login_failure(request: Request, username: str | None) -> None:
    """ثبت یک تلاش ناموفق در شمارنده‌های حافظه‌ای و مشترک."""
    ip = _client_ip(request)
    _LOGIN_IP.record(f"ip:{ip}")
    _LOGIN_ACCOUNT.record(f"acct:{ip}|{_identity_key(username)}")


def report_login_success(request: Request, username: str | None) -> None:
    """ورود موفق: بودجه‌ی همان (IP+شماره) بازمی‌گردد؛ بودجه‌ی IP نه."""
    _LOGIN_ACCOUNT.reset(f"acct:{_client_ip(request)}|{_identity_key(username)}")


# -----------------------------------------------------------
# تغییر رمز عبور (password change)
# -----------------------------------------------------------
def clear_password_change_counters() -> None:
    """فقط برای تست‌ها."""
    _PASSWORD_ACCOUNT.clear()


def password_change_guard(request: Request, username: str | None) -> None:
    """پیش از تغییر رمز: اگر بودجه‌ی حدسِ «رمز فعلی» تمام شده، 429."""
    allowed, retry_after = _PASSWORD_ACCOUNT.check(
        f"pwd:{_client_ip(request)}|{_identity_key(username)}"
    )
    if not allowed:
        raise _too_many_requests(retry_after)


def report_password_change_failure(request: Request, username: str | None) -> None:
    _PASSWORD_ACCOUNT.record(f"pwd:{_client_ip(request)}|{_identity_key(username)}")


def report_password_change_success(request: Request, username: str | None) -> None:
    _PASSWORD_ACCOUNT.reset(f"pwd:{_client_ip(request)}|{_identity_key(username)}")


# -----------------------------------------------------------
# نگهداری
# -----------------------------------------------------------
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