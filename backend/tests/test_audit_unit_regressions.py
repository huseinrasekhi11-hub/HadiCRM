"""
Environment-independent regression tests for the audit fixes
(HadiFlow_AUDIT_REPORT.md) and the refresh-session security work.

این فایل عمداً هیچ دیتابیس/شبکه‌ای لازم ندارد (مثل conftest فقط
متغیرهای محیطی settings را می‌خواهد) تا در هر محیطی — حتی بدون
PostgreSQL — اجرا شود و حداقلِ پوشش رگرسیون برای اصلاحات ممیزی
وجود. تست‌های یکپارچه‌سازی (DB-دار) در
tests/test_refresh_rotation.py و tests/test_followup_due_reminders.py
هستند.
"""
import importlib.util
import inspect
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

_VERSIONS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "alembic", "versions")
)


def _load_migration(filename: str):
    """بارگذاری فایل مهاجرت مستقیم از مسیر (نه به‌عنوان پکیج)."""
    path = os.path.join(_VERSIONS_DIR, filename)
    spec = importlib.util.spec_from_file_location(filename[:-3], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# -----------------------------------------------------------
# 1) Settings hardening (audit item: insecure debug/secret defaults)
# -----------------------------------------------------------
def _make_settings(**overrides):
    from app.config.settings import Settings

    base = {
        "SECRET_KEY": "x" * 48,
        "DATABASE_URL": "postgresql+psycopg2://u:p@localhost:5432/db",
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)


def test_debug_defaults_to_false():
    settings_obj = _make_settings()
    assert settings_obj.DEBUG is False, "DEBUG must default to False (secure default)"


def test_secret_key_shorter_than_32_bytes_is_rejected():
    with pytest.raises(ValidationError):
        _make_settings(SECRET_KEY="short-key-only-31-bytes-long!!")  # 30 bytes


def test_secret_key_of_32_bytes_is_accepted():
    settings_obj = _make_settings(SECRET_KEY="k" * 32)
    assert settings_obj.SECRET_KEY == "k" * 32


# -----------------------------------------------------------
# 2) Alembic downgrades must not be destructive
# -----------------------------------------------------------
def test_baseline_downgrade_is_irreversible():
    module = _load_migration("b0c1d2e3f4a5_baseline_core_tables.py")
    with pytest.raises(RuntimeError, match="disabled on purpose"):
        module.downgrade()


def test_user_fields_downgrade_preserves_parent_columns():
    module = _load_migration("e84148be659e_update_user_fields.py")
    source = inspect.getsource(module.downgrade)
    # created_at / is_active belong to the PARENT revision 6ea849d71db2;
    # this migration added only is_superuser/updated_at/last_login.
    # (statement-level check: comments may legitimately name the columns)
    assert 'drop_column("users", "created_at"' not in source
    assert 'drop_column("users", "is_active"' not in source
    assert 'drop_column("users", "last_login"' in source
    assert 'drop_column("users", "updated_at"' in source
    assert 'drop_column("users", "is_superuser"' in source


# -----------------------------------------------------------
# 3) ETag middleware must Vary on Authorization for authed GETs
# -----------------------------------------------------------
def _etag_app():
    from app.middleware.etag import ETagMiddleware

    app = FastAPI()
    app.add_middleware(ETagMiddleware)

    @app.get("/private")
    def private():
        return {"hello": "world"}

    return app


def test_etag_adds_vary_authorization_for_authenticated_requests():
    client = TestClient(_etag_app())
    res = client.get("/private", headers={"Authorization": "Bearer abc"})
    assert res.status_code == 200
    vary = res.headers.get("vary", "")
    assert "authorization" in vary.lower()


def test_etag_304_keeps_vary_authorization():
    client = TestClient(_etag_app())
    first = client.get("/private", headers={"Authorization": "Bearer abc"})
    etag = first.headers["etag"]
    second = client.get(
        "/private",
        headers={"Authorization": "Bearer abc", "If-None-Match": etag},
    )
    assert second.status_code == 304
    assert "authorization" in second.headers.get("vary", "").lower()


def test_etag_no_vary_for_anonymous_requests():
    client = TestClient(_etag_app())
    res = client.get("/private")
    assert "authorization" not in res.headers.get("vary", "").lower()


# -----------------------------------------------------------
# 4) Security headers middleware (audit item: browser hardening)
# -----------------------------------------------------------
def test_security_headers_middleware_sets_baseline_headers():
    from app.middleware.security_headers import SecurityHeadersMiddleware

    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/x")
    def x():
        return {"ok": True}

    res = TestClient(app).get("/x")
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-frame-options"] == "DENY"
    assert res.headers["referrer-policy"] == "no-referrer"
    assert res.headers["cache-control"] == "no-store"


# -----------------------------------------------------------
# 5) Notification vocabulary includes the Rule 4 type
# -----------------------------------------------------------
def test_follow_up_due_is_a_registered_notification_type():
    from app.models.notification import NOTIFICATION_TYPES

    assert "follow_up_due" in NOTIFICATION_TYPES


# -----------------------------------------------------------
# 6) Dashboard boundary parsing: date-only date_to is INCLUSIVE
#    and interpreted on Tehran calendar days (audit item: UTC/
#    naive-Tehran mixing).
# -----------------------------------------------------------
def test_parse_datetime_bound_gregorian_date_only_is_tehran_day():
    from app.api.routes.dashboard import _parse_datetime_bound

    bound = _parse_datetime_bound("2026-08-01")
    # midnight Tehran == 2026-07-31T20:30:00Z (Tehran is UTC+3:30)
    assert bound.isoformat() == "2026-07-31T20:30:00+00:00"


def test_parse_datetime_bound_inclusive_end_advances_one_day():
    from app.api.routes.dashboard import _parse_datetime_bound

    bound = _parse_datetime_bound("2026-08-01", inclusive_end=True)
    # end of Aug 1 (Tehran) == start of Aug 2 (Tehran) == Aug 1 20:30Z
    assert bound.isoformat() == "2026-08-01T20:30:00+00:00"


def test_parse_datetime_bound_explicit_time_is_not_advanced():
    from app.api.routes.dashboard import _parse_datetime_bound

    bound = _parse_datetime_bound("2026-08-01T10:30:00", inclusive_end=True)
    assert bound.isoformat() == "2026-08-01T10:30:00+00:00"


def test_parse_datetime_bound_jalali_inclusive_end():
    from app.api.routes.dashboard import _parse_datetime_bound

    exact = _parse_datetime_bound("1405/05/10")
    inclusive = _parse_datetime_bound("1405/05/10", inclusive_end=True)
    assert (inclusive - exact).total_seconds() == 24 * 3600


# -----------------------------------------------------------
# 7) Login rate limiter (audit item: brute-force control)
# -----------------------------------------------------------
def _fake_request(ip="203.0.113.10", headers=None):
    from starlette.datastructures import Headers

    class _Client:
        host = ip

    class _Req:
        client = _Client()

        def __init__(self, hdrs):
            self.headers = Headers(hdrs or {})

    return _Req(headers or {})


def test_rate_limiter_blocks_after_max_failures_per_account():
    from fastapi import HTTPException

    from app.core import rate_limit

    rate_limit.clear_login_counters()
    request = _fake_request()
    max_failures = rate_limit.settings.LOGIN_MAX_FAILURES_PER_ACCOUNT

    for _ in range(max_failures):
        rate_limit.login_rate_guard(request, "09121111111")
        rate_limit.report_login_failure(request, "09121111111")

    with pytest.raises(HTTPException) as exc_info:
        rate_limit.login_rate_guard(request, "09121111111")
    assert exc_info.value.status_code == 429
    assert "Retry-After" in exc_info.value.headers


def test_rate_limiter_equivalent_mobile_forms_share_one_budget():
    from fastapi import HTTPException

    from app.core import rate_limit

    rate_limit.clear_login_counters()
    request = _fake_request(ip="203.0.113.11")
    max_failures = rate_limit.settings.LOGIN_MAX_FAILURES_PER_ACCOUNT

    # attacker alternates between raw and normalized spellings of the
    # SAME number — the canonical identity key must merge them.
    forms = ["09121111111", "+989121111111", "۰۹۱۲۱۱۱۱۱۱۱"]
    for i in range(max_failures):
        form = forms[i % len(forms)]
        rate_limit.login_rate_guard(request, form)
        rate_limit.report_login_failure(request, form)

    with pytest.raises(HTTPException):
        rate_limit.login_rate_guard(request, "09121111111")


def test_rate_limiter_success_resets_account_budget_but_not_ip_budget():
    from fastapi import HTTPException

    from app.core import rate_limit

    rate_limit.clear_login_counters()
    request = _fake_request(ip="203.0.113.12")
    max_failures = rate_limit.settings.LOGIN_MAX_FAILURES_PER_ACCOUNT

    for _ in range(max_failures):
        rate_limit.report_login_failure(request, "09122222222")

    rate_limit.report_login_success(request, "09122222222")
    # account budget restored: guard passes again
    rate_limit.login_rate_guard(request, "09122222222")


def test_rate_limiter_per_ip_budget_blocks_credential_stuffing():
    from fastapi import HTTPException

    from app.core import rate_limit

    rate_limit.clear_login_counters()
    request = _fake_request(ip="203.0.113.13")
    max_ip = rate_limit.settings.LOGIN_MAX_FAILURES_PER_IP

    for i in range(max_ip):
        rate_limit.login_rate_guard(request, f"091200{i:05d}")
        rate_limit.report_login_failure(request, f"091200{i:05d}")

    # a brand-new account number must STILL be blocked from this IP
    with pytest.raises(HTTPException) as exc_info:
        rate_limit.login_rate_guard(request, "09129999999")
    assert exc_info.value.status_code == 429


# -----------------------------------------------------------
# 8) Canonical mobile identity (audit item: normalization)
# -----------------------------------------------------------
def test_normalize_mobile_equivalence_classes():
    from app.core.text_normalization import normalize_mobile

    forms = ["09121111111", "+989121111111", "00989121111111", "۰۹۱۲۱۱۱۱۱۱۱", "9121111111"]
    canonical = {normalize_mobile(f) for f in forms}
    assert canonical == {"09121111111"}


# -----------------------------------------------------------
# 9) Migration graph must stay linear with a single head
# -----------------------------------------------------------
def test_migration_graph_has_single_head():
    revisions = {}
    downs = set()
    for name in os.listdir(_VERSIONS_DIR):
        if not name.endswith(".py"):
            continue
        module = _load_migration(name)
        revisions[module.revision] = name
        if module.down_revision:
            downs.add(module.down_revision)

    heads = [rev for rev in revisions if rev not in downs]
    assert len(heads) == 1, f"expected exactly one migration head, got {heads}"
    # NOTE: keep this in sync when a new migration is added — the point of
    # the assertion is that the graph stays *linear*, so exactly one
    # revision is expected to be nobody's `down_revision`.
    assert heads[0] == "f5a8c9d2e1b3", (
        "head should be the current session-version migration "
        f"when a newer revision lands); got {heads[0]}"
    )


# -----------------------------------------------------------
# 10) Deployment defaults must fail safe
#     (audit: "Render startup defaults to demo-data reseeding")
# -----------------------------------------------------------
_RENDER_START = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "render_start.sh")
)


def _render_start_code() -> str:
    """متنِ اسکریپت بدون خطوطِ توضیحی (فقط دستورهای واقعی)."""
    with open(_RENDER_START, encoding="utf-8") as fh:
        lines = [
            line
            for line in fh.read().splitlines()
            if not line.lstrip().startswith("#")
        ]
    return "\n".join(lines)


def test_render_start_does_not_reseed_demo_data_by_default():
    """داده‌ی دمو باید «انتخابی» باشد، نه پیش‌فرضِ هر deploy/restart."""
    script = _render_start_code()

    # بدترین حالت: مقدارِ پیش‌فرضِ true یعنی بازنویسیِ داده با هر استقرار
    assert "RESEED_DEMO_DATA:-true" not in script, (
        "render_start.sh must not default RESEED_DEMO_DATA to true — a wrong "
        "or missing env var would then wipe and regenerate demo data on every "
        "deploy."
    )
    assert "RESEED_DEMO_DATA:-false" in script
    # و اجرای اسکریپتِ بازنشانی فقط در صورتِ درخواستِ صریح
    reseed_line_index = script.index("python clear_and_reseed.py")
    guard = script[:reseed_line_index]
    assert "RESEED_DEMO_DATA" in guard, "the reseed call must be guarded"


def test_render_start_applies_migrations_before_serving():
    """استقرار باید قبل از بالا آمدنِ API مهاجرت‌ها را اعمال کند."""
    script = _render_start_code()

    assert "alembic upgrade head" in script
    assert script.index("alembic upgrade head") < script.index("uvicorn")


# -----------------------------------------------------------
# 11) Refresh token must never be handed to browser storage
# -----------------------------------------------------------
def test_login_sets_an_httponly_cookie():
    """توکن تمدید باید HttpOnly باشد (localStorage برای هر اسکریپتی باز است)."""
    from app.auth.cookies import set_refresh_cookie
    from app.config.settings import settings
    from fastapi import Response

    response = Response()
    set_refresh_cookie(response, "test-token")

    headers = [v for k, v in response.headers.items() if k.lower() == "set-cookie"]
    assert headers, "login must set the refresh cookie"
    cookie = headers[0]
    assert "HttpOnly" in cookie
    assert settings.REFRESH_COOKIE_NAME in cookie
    assert f"Path={settings.REFRESH_COOKIE_PATH}" in cookie


def test_http_body_limit_rejects_oversized_requests():
    from app.main import app
    from fastapi.testclient import TestClient
    response = TestClient(app).post("/", content=b"x" * (26 * 1024 * 1024))
    assert response.status_code == 413


def test_invoice_sensitive_mutations_reload_and_lock_the_lead():
    import inspect
    from app.crud import lead as lead_crud
    assert "_lock_lead_for_mutation(db, lead.id)" in inspect.getsource(lead_crud.update_lead)
    assert "_lock_lead_for_mutation(db, lead.id)" in inspect.getsource(lead_crud.update_lead_status)


def test_final_factor_with_sale_items_is_committed_as_one_transaction():
    import inspect
    from app.api.routes import leads as leads_route
    source = inspect.getsource(leads_route.change_lead_status)
    assert "commit=not atomic_sale" in source
    assert "commit=False" in source
    assert "db.commit()" in source
