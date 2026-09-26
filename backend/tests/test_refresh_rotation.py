"""
Integration tests: server-side refresh-token revocation/rotation,
logout, deactivation revocation, canonical mobile identity and
login rate limiting.

این تست‌ها همان سه ضعف امنیتیِ «باقی‌مانده» در گزارش ممیزی
(HadiFlow_AUDIT_REPORT.md) را پوشش می‌دهند:
  1. HIGH — refresh-token replay / نبودِ revocation سمت سرور
  2. HIGH — نبودِ rate limiting روی /auth/login
  3. MEDIUM — هویت موبایل کاربر نرمال‌سازی نمی‌شد

نیاز به PostgreSQL واقعی + کاربر ادمین seed‌شده دارند
(09120000000 / Admin123! — همان قرارداد بقیه‌ی تست‌های یکپارچه‌سازی).
"""
from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth.jwt_handler import TOKEN_TYPE_REFRESH, verify_token
from app.config.settings import settings
from app.core import rate_limit
from app.database.database import SessionLocal
from app.main import app
from app.models.refresh_session import RefreshSession
from app.models.user import User

client = TestClient(app)

ADMIN_MOBILE = "09120000000"
ADMIN_PASSWORD = "Admin123!"


def unique_mobile(prefix: str = "0913") -> str:
    return f"{prefix}{str(uuid4().int)[:7]}"


def _admin_headers() -> dict:
    res = client.post(
        "/auth/login",
        data={"username": ADMIN_MOBILE, "password": ADMIN_PASSWORD},
    )
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _login(mobile: str, password: str):
    return client.post("/auth/login", data={"username": mobile, "password": password})


def _refresh(refresh_token: str):
    return client.post("/auth/refresh-token", json={"refresh_token": refresh_token})


def _jti_of(refresh_token: str) -> str:
    payload = verify_token(refresh_token, expected_type=TOKEN_TYPE_REFRESH)
    assert payload is not None, "refresh token must be a valid signed refresh JWT"
    return payload["jti"]


def _session_row(jti: str) -> RefreshSession | None:
    db = SessionLocal()
    try:
        return db.query(RefreshSession).filter(RefreshSession.jti == jti).first()
    finally:
        db.close()


# -----------------------------------------------------------
# 1) Login must persist a server-side session for the jti
# -----------------------------------------------------------
def test_login_creates_server_side_refresh_session():
    res = _login(ADMIN_MOBILE, ADMIN_PASSWORD)
    assert res.status_code == 200
    refresh_token = res.json()["refresh_token"]

    row = _session_row(_jti_of(refresh_token))
    assert row is not None, "refresh token jti must be persisted server-side"
    assert row.revoked_at is None
    assert row.expires_at is not None


# -----------------------------------------------------------
# 2) Refresh must ROTATE: new tokens, old session revoked
# -----------------------------------------------------------
def test_refresh_rotates_tokens():
    res = _login(ADMIN_MOBILE, ADMIN_PASSWORD)
    old_refresh = res.json()["refresh_token"]
    old_jti = _jti_of(old_refresh)

    res = _refresh(old_refresh)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["access_token"]
    new_refresh = body["refresh_token"]
    assert new_refresh != old_refresh, "refresh token must rotate on every use"

    old_row = _session_row(old_jti)
    assert old_row.revoked_at is not None
    assert old_row.revoked_reason == "rotated"
    assert old_row.replaced_by_jti == _jti_of(new_refresh)

    # the rotated token itself works (chain continues)
    res2 = _refresh(new_refresh)
    assert res2.status_code == 200, res2.text


# -----------------------------------------------------------
# 3) Replay of a consumed token must kill the whole family
# -----------------------------------------------------------
def test_reuse_of_consumed_token_revokes_entire_family():
    res = _login(ADMIN_MOBILE, ADMIN_PASSWORD)
    first = res.json()["refresh_token"]

    res = _refresh(first)
    assert res.status_code == 200
    second = res.json()["refresh_token"]

    # attacker (or a stale client) replays the consumed first token
    res = _refresh(first)
    assert res.status_code == 401

    # reuse detection must revoke the family: even the legitimate
    # rotated token is dead now — recovery is a fresh login.
    res = _refresh(second)
    assert res.status_code == 401

    db = SessionLocal()
    try:
        family_rows = (
            db.query(RefreshSession)
            .filter(RefreshSession.jti.in_([_jti_of(first), _jti_of(second)]))
            .all()
        )
        reasons = {row.revoked_reason for row in family_rows}
        assert "reuse_detected" in reasons
    finally:
        db.close()


# -----------------------------------------------------------
# 4) Logout must revoke server-side (not just localStorage)
# -----------------------------------------------------------
def test_logout_revokes_refresh_session():
    res = _login(ADMIN_MOBILE, ADMIN_PASSWORD)
    refresh_token = res.json()["refresh_token"]

    res = client.post("/auth/logout", json={"refresh_token": refresh_token})
    assert res.status_code == 204

    assert _refresh(refresh_token).status_code == 401


def test_logout_is_silent_for_unknown_or_invalid_tokens():
    # no session-state oracle: garbage tokens still get 204
    res = client.post("/auth/logout", json={"refresh_token": "not.a.jwt"})
    assert res.status_code == 204


def test_logout_twice_is_idempotent():
    res = _login(ADMIN_MOBILE, ADMIN_PASSWORD)
    refresh_token = res.json()["refresh_token"]
    assert client.post("/auth/logout", json={"refresh_token": refresh_token}).status_code == 204
    assert client.post("/auth/logout", json={"refresh_token": refresh_token}).status_code == 204


# -----------------------------------------------------------
# 5) Deactivating a user must cut their live sessions
# -----------------------------------------------------------
def test_deactivated_user_refresh_sessions_are_revoked():
    headers = _admin_headers()
    mobile = unique_mobile("0914")
    res = client.post(
        "/users/",
        headers=headers,
        json={
            "full_name": "Rotation Test User",
            "mobile": mobile,
            "password": "StrongPass!123",
            "role": "sales",
        },
    )
    assert res.status_code == 201, res.text
    user_id = res.json()["id"]

    res = _login(mobile, "StrongPass!123")
    assert res.status_code == 200, res.text
    refresh_token = res.json()["refresh_token"]

    res = client.put(
        f"/users/{user_id}",
        headers=headers,
        json={"is_active": False},
    )
    assert res.status_code == 200, res.text

    # the live refresh token must be dead immediately
    assert _refresh(refresh_token).status_code == 401
    # and login returns the uniform 401 (no account-state leak)
    assert _login(mobile, "StrongPass!123").status_code == 401


# -----------------------------------------------------------
# 6) Canonical mobile identity
# -----------------------------------------------------------
def test_user_can_login_with_any_equivalent_mobile_form():
    headers = _admin_headers()
    base = unique_mobile("0915")            # 0915xxxxxxx
    intl = f"+98{base[1:]}"                 # +98915xxxxxxx

    res = client.post(
        "/users/",
        headers=headers,
        json={
            "full_name": "Canonical Mobile User",
            "mobile": intl,
            "password": "StrongPass!123",
            "role": "sales",
        },
    )
    assert res.status_code == 201, res.text

    # stored raw as +98…, but login with the plain 09… form must work
    res = _login(base, "StrongPass!123")
    assert res.status_code == 200, res.text

    # a second account with an equivalent number must be refused
    res = client.post(
        "/users/",
        headers=headers,
        json={
            "full_name": "Impostor",
            "mobile": f"0098{base[1:]}",
            "password": "StrongPass!123",
            "role": "sales",
        },
    )
    assert res.status_code == 400
    assert "exists" in res.json()["detail"].lower() or "Mobile" in res.json()["detail"]


def test_mobile_normalized_column_is_populated():
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.mobile == ADMIN_MOBILE).first()
        assert admin is not None
        assert admin.mobile_normalized == ADMIN_MOBILE
    finally:
        db.close()


# -----------------------------------------------------------
# 7) Login rate limiting (brute-force control)
# -----------------------------------------------------------
def test_login_is_rate_limited_after_repeated_failures():
    rate_limit.clear_login_counters()
    try:
        mobile = unique_mobile("0916")
        max_failures = settings.LOGIN_MAX_FAILURES_PER_ACCOUNT

        for _ in range(max_failures):
            res = _login(mobile, "wrong-password")
            assert res.status_code == 401

        res = _login(mobile, "wrong-password")
        assert res.status_code == 429
        assert "Retry-After" in res.headers

        # even the CORRECT password is locked out while the budget is spent
        # (account does not exist here, but the guard runs before lookup)
        res = _login(mobile, "whatever")
        assert res.status_code == 429
    finally:
        rate_limit.clear_login_counters()


def test_successful_login_restores_account_budget():
    rate_limit.clear_login_counters()
    try:
        # burn most of the admin account's failure budget
        for _ in range(settings.LOGIN_MAX_FAILURES_PER_ACCOUNT - 1):
            assert _login(ADMIN_MOBILE, "wrong-password").status_code == 401

        # one success resets the per-account budget
        assert _login(ADMIN_MOBILE, ADMIN_PASSWORD).status_code == 200

        for _ in range(settings.LOGIN_MAX_FAILURES_PER_ACCOUNT - 1):
            assert _login(ADMIN_MOBILE, "wrong-password").status_code == 401
    finally:
        rate_limit.clear_login_counters()
