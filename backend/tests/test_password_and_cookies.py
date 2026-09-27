"""
Integration tests: password change/reset + HttpOnly refresh cookie.

دو مورد از یافته‌های بازِ گزارش ممیزی را می‌پوشاند:

  1. MEDIUM — «No password change/reset endpoint exists for anyone,
     including admins»:
       POST /auth/change-password   (خودِ کاربر، با دانشِ رمز فعلی)
       POST /users/{id}/reset-password (ادمین/مدیرعامل، رمزِ موقت)
     هر دو نشست‌های تمدید را باطل و رویداد را در audit_log ثبت می‌کنند.

  2. MEDIUM — «Access and refresh tokens are still in localStorage»:
     توکن تمدید حالا در کوکیِ HttpOnly است (نه localStorage) و مسیرِ
     refresh/logout بدون بدنه و فقط با کوکی کار می‌کند؛ در برابرِ درخواستِ
     بین‌سایتیِ جعلی (CSRF) هم محافظت شده است.

نیاز به PostgreSQL واقعی + کاربر ادمین seed‌شده (09120000000 / Admin123!).
"""
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config.settings import settings
from app.core import rate_limit
from app.database.database import SessionLocal
from app.main import app
from app.models.audit_log import AuditLog
from app.models.refresh_session import RefreshSession

# کلاینتِ HTTPS: کوکیِ Secure فقط روی https ارسال می‌شود (رفتارِ مرورگر)
client = TestClient(app, base_url="https://testserver")

ADMIN_MOBILE = "09120000000"
ADMIN_PASSWORD = "Admin123!"
COOKIE_NAME = settings.REFRESH_COOKIE_NAME


def unique_mobile(prefix: str = "0918") -> str:
    return f"{prefix}{str(uuid4().int)[:7]}"


def _login(mobile: str, password: str):
    return client.post("/auth/login", data={"username": mobile, "password": password})


def _admin_headers() -> dict:
    res = _login(ADMIN_MOBILE, ADMIN_PASSWORD)
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _create_user(password: str = "StrongPass!123") -> dict:
    headers = _admin_headers()
    res = client.post(
        "/users/",
        headers=headers,
        json={
            "full_name": "Password Test User",
            "mobile": unique_mobile(),
            "password": password,
            "role": "sales",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _sessions_for(user_id: int) -> list[RefreshSession]:
    db = SessionLocal()
    try:
        return (
            db.query(RefreshSession)
            .filter(RefreshSession.user_id == user_id)
            .all()
        )
    finally:
        db.close()


def _active_sessions(user_id: int) -> list[RefreshSession]:
    return [s for s in _sessions_for(user_id) if s.revoked_at is None]


# ===========================================================
# 1) HttpOnly refresh cookie
# ===========================================================
def test_login_sets_an_httponly_refresh_cookie():
    res = _login(ADMIN_MOBILE, ADMIN_PASSWORD)
    assert res.status_code == 200, res.text

    cookie_header = res.headers.get("set-cookie", "")
    assert COOKIE_NAME in cookie_header, cookie_header
    assert "HttpOnly" in cookie_header, "refresh cookie must be HttpOnly"
    assert "Secure" in cookie_header, "cookie must be Secure in production defaults"
    assert f"Path={settings.REFRESH_COOKIE_PATH}" in cookie_header
    assert "Max-Age=" in cookie_header
    assert "refresh_token" not in res.json(), "refresh token must never be exposed in JSON"


def test_refresh_works_without_a_body_using_the_cookie():
    client.cookies.clear()
    res = _login(ADMIN_MOBILE, ADMIN_PASSWORD)
    assert res.status_code == 200
    first_refresh = client.cookies.get(COOKIE_NAME)
    assert first_refresh

    # بدونِ بدنه — فقط با کوکی (همان کاری که مرورگر می‌کند)
    res = client.post("/auth/refresh-token", json={})
    assert res.status_code == 200, res.text
    new_refresh = client.cookies.get(COOKIE_NAME)
    assert new_refresh and new_refresh != first_refresh
    assert "refresh_token" not in res.json()

    # توکنِ قبلی مصرف شده است
    assert client.post(
        "/auth/logout", json={"refresh_token": first_refresh}
    ).status_code == 204


def test_refresh_cookie_is_rotated_on_every_use():
    client.cookies.clear()
    assert _login(ADMIN_MOBILE, ADMIN_PASSWORD).status_code == 200
    first_cookie = client.cookies.get(COOKIE_NAME)

    res = client.post("/auth/refresh-token", json={})
    assert res.status_code == 200, res.text
    assert client.cookies.get(COOKIE_NAME) != first_cookie


def test_refresh_rejects_a_cookie_request_from_a_foreign_origin():
    client.cookies.clear()
    assert _login(ADMIN_MOBILE, ADMIN_PASSWORD).status_code == 200

    res = client.post(
        "/auth/refresh-token",
        json={},
        headers={"Origin": "https://evil.example.com"},
    )
    assert res.status_code == 401, res.text


def test_refresh_accepts_a_cookie_request_from_an_allowed_origin():
    """محافظِ CSRF نباید درخواستِ مشروعِ فرانت‌اند را هم رد کند."""
    allowed = settings.cors_origin_list
    assert allowed, "CORS_ORIGINS must be configured for the panel"

    client.cookies.clear()
    assert _login(ADMIN_MOBILE, ADMIN_PASSWORD).status_code == 200

    res = client.post(
        "/auth/refresh-token",
        json={},
        headers={"Origin": allowed[0]},
    )
    assert res.status_code == 200, res.text


def test_refresh_accepts_a_preexisting_body_token_without_returning_one():
    client.cookies.clear()
    res = _login(ADMIN_MOBILE, ADMIN_PASSWORD)
    refresh_token = client.cookies.get(COOKIE_NAME)
    assert refresh_token

    client.cookies.clear()
    res = client.post("/auth/refresh-token", json={"refresh_token": refresh_token})
    assert res.status_code == 200, res.text
    assert "refresh_token" not in res.json()


def test_logout_without_body_clears_the_cookie_and_revokes_the_session():
    client.cookies.clear()
    assert _login(ADMIN_MOBILE, ADMIN_PASSWORD).status_code == 200

    res = client.post("/auth/logout")
    assert res.status_code == 204, res.text

    # نشستِ تمدید باطل شده است
    res = client.post("/auth/refresh-token", json={})
    assert res.status_code == 401


# ===========================================================
# 2) Self-service password change
# ===========================================================
def test_user_can_change_own_password():
    user = _create_user()
    mobile = user["mobile"]

    res = _login(mobile, "StrongPass!123")
    assert res.status_code == 200, res.text
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}

    res = client.post(
        "/auth/change-password",
        headers=headers,
        json={"current_password": "StrongPass!123", "new_password": "NewPass!2026"},
    )
    assert res.status_code == 200, res.text

    # رمزِ قدیمی دیگر کار نمی‌کند و رمزِ جدید کار می‌کند
    assert _login(mobile, "StrongPass!123").status_code == 401
    assert _login(mobile, "NewPass!2026").status_code == 200


def test_password_change_invalidates_old_access_token_and_returns_a_fresh_one():
    user = _create_user()
    logged = _login(user["mobile"], "StrongPass!123")
    assert logged.status_code == 200
    old_access = logged.json()["access_token"]
    headers = {"Authorization": f"Bearer {old_access}"}

    changed = client.post(
        "/auth/change-password",
        headers=headers,
        json={
            "current_password": "StrongPass!123",
            "new_password": "Fresh!2026",
        },
    )
    assert changed.status_code == 200, changed.text
    new_access = changed.json()["access_token"]
    assert new_access and new_access != old_access

    assert client.get("/auth/me", headers=headers).status_code == 401
    assert client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {new_access}"},
    ).status_code == 200


def test_change_password_requires_the_current_password():
    user = _create_user()
    res = _login(user["mobile"], "StrongPass!123")
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}

    res = client.post(
        "/auth/change-password",
        headers=headers,
        json={"current_password": "totally-wrong", "new_password": "Another!2026"},
    )
    assert res.status_code == 400, res.text

    # رمز تغییر نکرده است
    assert _login(user["mobile"], "StrongPass!123").status_code == 200


def test_change_password_rejects_a_short_new_password():
    user = _create_user()
    res = _login(user["mobile"], "StrongPass!123")
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}

    res = client.post(
        "/auth/change-password",
        headers=headers,
        json={"current_password": "StrongPass!123", "new_password": "123"},
    )
    assert res.status_code == 422, res.text
    assert _login(user["mobile"], "StrongPass!123").status_code == 200


def test_change_password_revokes_other_sessions_but_keeps_the_current_one():
    user = _create_user()
    user_id = user["id"]

    # نشستِ ۱: همین دستگاه (بعداً با کوکی حفظ می‌شود)
    client.cookies.clear()
    res = _login(user["mobile"], "StrongPass!123")
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}
    kept_refresh = client.cookies.get(COOKIE_NAME)
    assert kept_refresh

    # نشستِ ۲: دستگاهِ دیگر (کوکیِ جدا)
    other = TestClient(app, base_url="https://testserver")
    other_res = other.post(
        "/auth/login", data={"username": user["mobile"], "password": "StrongPass!123"}
    )
    assert other_res.status_code == 200
    other_refresh = other.cookies.get(COOKIE_NAME)
    assert other_refresh

    assert len(_active_sessions(user_id)) == 2

    res = client.post(
        "/auth/change-password",
        headers=headers,
        json={
            "current_password": "StrongPass!123",
            "new_password": "Rotated!2026",
        },
    )
    assert res.status_code == 200, res.text

    # نشستِ «دیگر» باطل شده ...
    assert other.post(
        "/auth/refresh-token", json={"refresh_token": other_refresh}
    ).status_code == 401
    # ... و نشستِ جاری زنده مانده است
    res = client.post("/auth/refresh-token", json={})
    assert res.status_code == 200, res.text


def test_password_change_is_rate_limited():
    user = _create_user()
    res = _login(user["mobile"], "StrongPass!123")
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}

    rate_limit.clear_password_change_counters()
    try:
        for _ in range(settings.PASSWORD_CHANGE_MAX_FAILURES):
            assert (
                client.post(
                    "/auth/change-password",
                    headers=headers,
                    json={
                        "current_password": "wrong-one",
                        "new_password": "Whatever!2026",
                    },
                ).status_code
                == 400
            )

        res = client.post(
            "/auth/change-password",
            headers=headers,
            json={"current_password": "wrong-one", "new_password": "Whatever!2026"},
        )
        assert res.status_code == 429
        assert "Retry-After" in res.headers
    finally:
        rate_limit.clear_password_change_counters()


def test_change_password_requires_authentication():
    res = client.post(
        "/auth/change-password",
        json={"current_password": "x", "new_password": "Whatever!2026"},
    )
    assert res.status_code == 401


# ===========================================================
# 3) Admin password reset
# ===========================================================
def test_admin_can_reset_another_users_password():
    headers = _admin_headers()
    user = _create_user()
    user_id = user["id"]

    # یک نشستِ فعال برای کاربر هدف
    res = _login(user["mobile"], "StrongPass!123")
    assert res.status_code == 200
    old_refresh = client.cookies.get(COOKIE_NAME)
    assert old_refresh

    res = client.post(
        f"/users/{user_id}/reset-password",
        headers=headers,
        json={"new_password": "TempPass!2026"},
    )
    assert res.status_code == 200, res.text

    # نشست‌های کاربر هدف باطل شده‌اند
    assert client.post(
        "/auth/refresh-token", json={"refresh_token": old_refresh}
    ).status_code == 401

    # رمزِ موقت کار می‌کند
    assert _login(user["mobile"], "TempPass!2026").status_code == 200


def test_admin_cannot_reset_own_password_through_the_admin_route():
    headers = _admin_headers()
    me = client.get("/auth/me", headers=headers).json()

    res = client.post(
        f"/users/{me['id']}/reset-password",
        headers=headers,
        json={"new_password": "TempPass!2026"},
    )
    assert res.status_code == 400, res.text
    # حسابِ ادمین دست‌نخورده است
    assert _login(ADMIN_MOBILE, ADMIN_PASSWORD).status_code == 200


def test_password_reset_requires_admin_role():
    user = _create_user()
    res = _login(user["mobile"], "StrongPass!123")
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}
    admin = client.get("/auth/me", headers=_admin_headers()).json()

    res = client.post(
        f"/users/{admin['id']}/reset-password",
        headers=headers,
        json={"new_password": "TempPass!2026"},
    )
    assert res.status_code == 403, res.text


def test_password_reset_is_written_to_the_audit_log():
    headers = _admin_headers()
    user = _create_user()

    db = SessionLocal()
    try:
        before = (
            db.query(AuditLog)
            .filter(AuditLog.action == "reset_password")
            .count()
        )
    finally:
        db.close()

    res = client.post(
        f"/users/{user['id']}/reset-password",
        headers=headers,
        json={"new_password": "TempPass!2026"},
    )
    assert res.status_code == 200, res.text

    db = SessionLocal()
    try:
        after = (
            db.query(AuditLog)
            .filter(AuditLog.action == "reset_password")
            .count()
        )
    finally:
        db.close()
    assert after == before + 1