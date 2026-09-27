"""
Integration/unit tests: the login brute-force budget must be SHARED.

گزارش ممیزی: «MEDIUM — login rate limiting is only per-process». شمارنده‌ی
قبلی فقط در حافظه‌ی فرایند بود، یعنی با ۴ worker/replica سقفِ مؤثرِ حدسِ
رمز چهار برابر می‌شد. این تست‌ها تثبیت می‌کنند که بودجه حالا در یک انبارِ
مشترک (دیتابیس) نگه داشته می‌شود:

  * شمارنده‌های حافظه‌ایِ یک فرایندِ دیگر (یک نمونه‌ی تازه از
    DatabaseRateLimiter) همان بودجه را می‌بینند؛
  * پاک‌کردنِ شمارنده‌های حافظه‌ایِ همین فرایند (شبیه‌سازیِ یک worker
    دیگر/فرایندِ تازه) بودجه را بازنمی‌گرداند؛
  * رویدادها واقعاً در جدول login_rate_events ثبت و بعد از گذرِ پنجره
    پاک/نادیده گرفته می‌شوند.
"""
import threading
import time
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.config.settings import settings
from app.core import rate_limit
from app.database.database import SessionLocal
from app.main import app
from app.models.login_rate_event import LoginRateEvent

client = TestClient(app)

ADMIN_MOBILE = "09120000000"
ADMIN_PASSWORD = "Admin123!"


def _login(mobile: str, password: str):
    return client.post("/auth/login", data={"username": mobile, "password": password})


def _event_rows(key_fragment: str | None = None) -> list[LoginRateEvent]:
    db = SessionLocal()
    try:
        query = db.query(LoginRateEvent)
        if key_fragment:
            query = query.filter(LoginRateEvent.event_key.contains(key_fragment))
        return query.all()
    finally:
        db.close()


def _fresh_shared_limiter(max_events: int | None = None) -> rate_limit.DatabaseRateLimiter:
    """
    یک نمونه‌ی کاملاً جدا — همان چیزی که یک worker/replica دیگر با حافظه‌ی
    مستقلِ خودش در اختیار دارد.
    """
    return rate_limit.DatabaseRateLimiter(
        session_factory=None,
        max_events=max_events or settings.LOGIN_MAX_FAILURES_PER_ACCOUNT,
        window_seconds=settings.LOGIN_RATE_WINDOW_SECONDS,
    )


# -----------------------------------------------------------
# 1) Failures are persisted in the shared store, not just memory
# -----------------------------------------------------------
def test_failed_logins_are_recorded_in_the_shared_store():
    rate_limit.clear_login_counters()
    try:
        mobile = "09170000001"
        for _ in range(2):
            assert _login(mobile, "wrong-password").status_code == 401

        rows = _event_rows("09170000001")
        assert len(rows) == 2, f"expected 2 persisted failures, got {rows}"
        assert all(r.created_at is not None for r in rows)
    finally:
        rate_limit.clear_login_counters()


# -----------------------------------------------------------
# 2) A second, independent limiter instance sees the same budget
# -----------------------------------------------------------
def test_independent_limiter_instances_share_the_budget():
    rate_limit.clear_login_counters()
    try:
        key = "acct:test-shared|09170000002"
        writer = _fresh_shared_limiter(max_events=3)
        reader = _fresh_shared_limiter(max_events=3)

        assert reader.check(key)[0] is True
        for _ in range(3):
            assert writer.record(key)[0] is True

        # نمونه‌ی «دیگر» (فرایندِ دیگر) بودجه را می‌بیند و مسدود می‌کند
        allowed, retry_after = reader.check(key)
        assert allowed is False, "budget must be visible to every process"
        assert retry_after >= 1

        # و ثبتِ بعدی هم مردود است
        assert writer.record(key)[0] is False
    finally:
        rate_limit.clear_login_counters()


# -----------------------------------------------------------
# 3) Clearing this process's memory does NOT restore the budget
#    (this is exactly the multi-worker hole)
# -----------------------------------------------------------
def test_clearing_process_memory_does_not_restore_the_budget():
    rate_limit.clear_login_counters()
    try:
        mobile = "09170000003"
        for _ in range(settings.LOGIN_MAX_FAILURES_PER_ACCOUNT):
            assert _login(mobile, "wrong-password").status_code == 401

        assert _login(mobile, "wrong-password").status_code == 429

        # شبیه‌سازیِ «فرایند/ریپلیکای تازه»: شمارنده‌های حافظه‌ای خالی‌اند،
        # اما بودجه‌ی مشترک هنوز مصرف شده است.
        rate_limit._LOGIN_ACCOUNT.clear_memory_only()
        rate_limit._LOGIN_IP.clear_memory_only()

        res = _login(mobile, "wrong-password")
        assert res.status_code == 429, (
            "a fresh process must NOT get a fresh brute-force budget"
        )
        assert "Retry-After" in res.headers
    finally:
        rate_limit.clear_login_counters()


# -----------------------------------------------------------
# 4) Successful login resets the shared per-account budget
# -----------------------------------------------------------
def test_successful_login_resets_shared_account_budget():
    rate_limit.clear_login_counters()
    try:
        for _ in range(settings.LOGIN_MAX_FAILURES_PER_ACCOUNT - 1):
            assert _login(ADMIN_MOBILE, "wrong-password").status_code == 401

        assert _login(ADMIN_MOBILE, ADMIN_PASSWORD).status_code == 200

        key_fragment = ADMIN_MOBILE
        assert _event_rows(key_fragment) == [], "success must clear the account budget"

        # بودجه دوباره پر شده است
        for _ in range(settings.LOGIN_MAX_FAILURES_PER_ACCOUNT - 1):
            assert _login(ADMIN_MOBILE, "wrong-password").status_code == 401
        assert _login(ADMIN_MOBILE, ADMIN_PASSWORD).status_code == 200
    finally:
        rate_limit.clear_login_counters()


# -----------------------------------------------------------
# 5) Events outside the sliding window are ignored/pruned
# -----------------------------------------------------------
def test_events_outside_the_window_are_not_counted():
    rate_limit.clear_login_counters()
    try:
        key = "acct:test-window|09170000005"
        limiter = rate_limit.DatabaseRateLimiter(
            session_factory=None, max_events=2, window_seconds=1
        )

        assert limiter.record(key)[0] is True
        assert limiter.record(key)[0] is True
        assert limiter.check(key)[0] is False

        time.sleep(1.2)

        assert limiter.check(key)[0] is True, "old events must fall out of the window"

        # رویدادهای کهنه هنگامِ ثبتِ بعدی پاک می‌شوند (عدم رشدِ بی‌پایانِ جدول)
        assert limiter.record(key)[0] is True
        rows = _event_rows(key)
        assert len(rows) == 1, f"stale events must be pruned, got {len(rows)}"
    finally:
        rate_limit.clear_login_counters()


# -----------------------------------------------------------
# 6) Per-IP budget guards credential stuffing across accounts
# -----------------------------------------------------------
def test_per_ip_budget_is_shared_too():
    rate_limit.clear_login_counters()
    try:
        shared_ip = rate_limit.DatabaseRateLimiter(
            session_factory=None,
            max_events=settings.LOGIN_MAX_FAILURES_PER_IP,
            window_seconds=settings.LOGIN_RATE_WINDOW_SECONDS,
        )
        ip_key = "ip:testclient"

        for i in range(settings.LOGIN_MAX_FAILURES_PER_IP):
            assert _login(f"0917001{i:04d}", "wrong-password").status_code in (401, 429)

        allowed, _retry = shared_ip.check(ip_key)
        assert allowed is False, "per-IP budget must be shared, not per-process"
    finally:
        rate_limit.clear_login_counters()


# -----------------------------------------------------------
# 7) Timestamps are timezone-aware UTC (naive/aware comparison bugs)
# -----------------------------------------------------------
def test_persisted_events_use_aware_utc_timestamps():
    rate_limit.clear_login_counters()
    try:
        limiter = _fresh_shared_limiter()
        before = datetime.now(timezone.utc)
        limiter.record("acct:test-tz|09170000007")
        rows = _event_rows("09170000007")
        assert len(rows) == 1
        created = rows[0].created_at
        assert created.tzinfo is not None, "created_at must be timezone-aware"
        assert created >= before - timedelta(seconds=5)
    finally:
        rate_limit.clear_login_counters()

def test_shared_limiter_never_exceeds_budget_under_concurrency():
    rate_limit.clear_login_counters()
    try:
        limiter = rate_limit.DatabaseRateLimiter(
            session_factory=None,
            max_events=3,
            window_seconds=60,
        )
        key = "acct:concurrency|09170000008"
        barrier = threading.Barrier(5)
        results = []
        lock = threading.Lock()

        def worker():
            barrier.wait(timeout=15)
            outcome = limiter.record(key)[0]
            with lock:
                results.append(outcome)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert not any(thread.is_alive() for thread in threads)
        assert results.count(True) == 3
        assert results.count(False) == 2
        assert len(_event_rows(key)) == 3
    finally:
        rate_limit.clear_login_counters()


def test_untrusted_forwarded_for_is_ignored():
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/auth/login",
        "headers": [(b"x-forwarded-for", b"203.0.113.10")],
        "client": ("198.51.100.20", 12345),
        "server": ("testserver", 443),
        "scheme": "https",
    }
    request = Request(scope)
    assert rate_limit._client_ip(request) == "198.51.100.20"
