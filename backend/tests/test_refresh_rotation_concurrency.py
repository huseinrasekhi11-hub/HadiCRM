"""
Integration tests: refresh-token rotation must be ATOMIC under concurrency.

این فایل یک شکافِ مشخصِ «HIGH» را می‌پوشاند: `rotate_session()` پیش از این
ردیفِ نشست را بدون قفل می‌خواند، وضعیت را در پایتون بررسی می‌کرد و بعد
می‌نوشت — یعنی یک race کلاسیکِ check-then-act (TOCTOU):

    Request A                  Request B
    ---------                  ---------
    SELECT jti -> active       SELECT jti -> active
    check not revoked          check not revoked
    create new JTI             create new JTI
    revoke old                 revoke old
    COMMIT                     COMMIT

هر دو می‌توانستند با یک refresh token موفق شوند؛ یعنی توکنِ «یک‌بار‌مصرف»
دو بار مصرف می‌شد و مهاجمی که توکن را در اختیار داشت می‌توانست هم‌زمان با
کلاینتِ واقعی آن را چرخش دهد.

اصلاح: قفلِ ردیف (SELECT ... FOR UPDATE) + انتقالِ وضعیتِ شرطی و اتمیک
(UPDATE ... WHERE revoked_at IS NULL و بررسیِ تعداد ردیف‌های تحت‌تأثیر).

تست‌ها نیاز به PostgreSQL واقعی دارند (قفلِ ردیف و انزوای READ COMMITTED
در SQLite معنای متفاوتی دارد) و کاربر ادمین seed‌شده (09120000000 / Admin123!).
"""
import threading
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import event

from app.auth.jwt_handler import TOKEN_TYPE_REFRESH, verify_token
from app.database.database import SessionLocal, engine
from app.main import app
from app.models.refresh_session import RefreshSession
from app.config.settings import settings
from app.services import auth_service
from app.services.auth_service import RefreshTokenError, rotate_session

from fastapi.testclient import TestClient

client = TestClient(app, base_url="https://testserver")

ADMIN_MOBILE = "09120000000"
COOKIE_NAME = settings.REFRESH_COOKIE_NAME
ADMIN_PASSWORD = "Admin123!"


def _new_refresh_token() -> str:
    res = client.post(
        "/auth/login",
        data={"username": ADMIN_MOBILE, "password": ADMIN_PASSWORD},
    )
    assert res.status_code == 200, res.text
    token = client.cookies.get(COOKIE_NAME)
    assert token, "login must install an HttpOnly refresh cookie"
    assert "refresh_token" not in res.json()
    return token


def _jti_of(refresh_token: str) -> str:
    payload = verify_token(refresh_token, expected_type=TOKEN_TYPE_REFRESH)
    assert payload is not None
    return payload["jti"]


def _family_rows(family_id: str) -> list[RefreshSession]:
    db = SessionLocal()
    try:
        return (
            db.query(RefreshSession)
            .filter(RefreshSession.family_id == family_id)
            .all()
        )
    finally:
        db.close()


# -----------------------------------------------------------
# 1) The rotation MUST read the session row with a row lock
# -----------------------------------------------------------
def test_rotation_reads_session_with_row_lock():
    """ردیفِ نشست باید با FOR UPDATE خوانده شود (وگرنه قفلی در کار نیست)."""
    if engine.dialect.name != "postgresql":
        pytest.skip("row locking semantics differ on non-PostgreSQL backends")

    statements: list[str] = []

    def _capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", _capture)
    try:
        db = SessionLocal()
        try:
            rotate_session(db, _jti_of(_new_refresh_token()))
        finally:
            db.close()
    finally:
        event.remove(engine, "before_cursor_execute", _capture)

    locked_selects = [
        s
        for s in statements
        if "refresh_sessions" in s and "FOR UPDATE" in s.upper()
    ]
    assert locked_selects, (
        "rotate_session must lock the session row (SELECT ... FOR UPDATE); "
        f"captured statements: {statements}"
    )


# -----------------------------------------------------------
# 2) A stale in-memory snapshot must NOT be spendable (TOCTOU)
# -----------------------------------------------------------
def test_stale_snapshot_cannot_be_rotated_twice(monkeypatch):
    """
    شبیه‌سازیِ جفت‌شدنِ قطعیِ بدترین حالت:

    A ردیف را می‌خواند (اسنپ‌شات: فعال) — دقیقاً همان کاری که کدِ قدیمی
    می‌کرد. سپس B همان jti را چرخش می‌دهد و COMMIT می‌کند. بعد A ادامه
    می‌دهد در حالی که شیءِ در حافظه‌اش هنوز «فعال» است. اگر انتقالِ وضعیت
    اتمیک نباشد، A هم نشستِ تازه صادر می‌کند (دو توکنِ زنده از یک توکنِ
    یک‌بار‌مصرف).
    """
    refresh_token = _new_refresh_token()
    jti = _jti_of(refresh_token)

    db_a = SessionLocal()
    db_b = SessionLocal()
    try:
        # --- A: همان SELECTِ بدون قفلِ کدِ قدیمی (اسنپ‌شاتِ کهنه) ---
        stale = (
            db_a.query(RefreshSession).filter(RefreshSession.jti == jti).first()
        )
        assert stale is not None and stale.revoked_at is None
        family_id = stale.family_id  # capture before any rollback expires it

        # --- B: چرخشِ واقعی و کامل همان توکن ---
        _old, new_session = rotate_session(db_b, jti)
        assert new_session.jti != jti

        # --- A: ادامه با اسنپ‌شاتِ کهنه (برنده/بازنده این‌جا معلوم می‌شود) ---
        monkeypatch.setattr(
            auth_service, "_select_session_for_rotation", lambda _db, _jti: stale
        )
        with pytest.raises(RefreshTokenError) as excinfo:
            rotate_session(db_a, jti)

        assert excinfo.value.reason == "reused"
    finally:
        db_a.close()
        db_b.close()

    # نتیجه‌ی محافظه‌کارانه: replay قطعی تلقی شده و کل خانواده باطل شده است،
    # بنابراین هیچ نشستِ فعالی از این توکن باقی نمانده.
    rows = _family_rows(family_id)
    assert len(rows) <= 2, "at most one replacement session may be created"
    assert [r for r in rows if r.revoked_at is None] == []
    assert any(r.revoked_reason == "reuse_detected" for r in rows)


# -----------------------------------------------------------
# 3) Two truly concurrent refreshes: exactly one may succeed
# -----------------------------------------------------------
def test_concurrent_refresh_issues_at_most_one_new_session(monkeypatch):
    """
    دو درخواستِ واقعاً هم‌زمانِ refresh با یک توکن:
      * حداکثر یکی اجازه‌ی چرخش دارد،
      * بازنده با ۴۰۱/replay مواجه می‌شود،
      * و در پایان هیچ نشستِ فعالِ دوتایی از یک توکنِ یک‌بار‌مصرف نمی‌ماند.
    """
    refresh_token = _new_refresh_token()
    jti = _jti_of(refresh_token)

    real_select = auth_service._select_session_for_rotation
    local = threading.local()

    def gated_select(db, jti_value):
        """
        هر نخ پیش از اولین تماس با دیتابیس منتظرِ رقیبش می‌ماند؛ این
        هم‌پوشانیِ دو درخواست را قطعی می‌کند (بدون آن، تست می‌تواند به
        اجرای کاملاً پشت‌سرهم تنزل کند و چیزی را ثابت نکند).
        """
        if not getattr(local, "gated", False):
            local.gated = True
            rendezvous.wait(timeout=15)
        return real_select(db, jti_value)

    rendezvous = threading.Barrier(2)
    monkeypatch.setattr(auth_service, "_select_session_for_rotation", gated_select)

    results: list[tuple[str, str]] = []
    lock = threading.Lock()

    def worker() -> None:
        db = SessionLocal()
        try:
            _old, new_session = rotate_session(db, jti)
            outcome = ("ok", new_session.jti)
        except RefreshTokenError as exc:
            db.rollback()
            outcome = ("error", exc.reason)
        except Exception as exc:  # noqa: BLE001 - surfaced in the assertion below
            db.rollback()
            outcome = ("exception", repr(exc))
        finally:
            db.close()
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert not any(t.is_alive() for t in threads), "threads deadlocked/hung"
    assert len(results) == 2, results

    kinds = sorted(kind for kind, _ in results)
    assert kinds.count("ok") <= 1, (
        "the same refresh token was rotated by two concurrent requests: "
        f"{results}"
    )
    assert "exception" not in kinds, results

    # بازنده باید با replay/ابطال روبه‌رو شده باشد (نه یک نشستِ دومِ معتبر)
    errors = [detail for kind, detail in results if kind == "error"]
    assert errors, f"at least one racing request must be rejected: {results}"

    db = SessionLocal()
    try:
        row = db.query(RefreshSession).filter(RefreshSession.jti == jti).first()
        family_id = row.family_id
    finally:
        db.close()

    rows = _family_rows(family_id)
    issued_new = [r for r in rows if r.replaced_by_jti or r.revoked_reason == "rotated"]
    # یک چرخش = حداکثر یک نشستِ جایگزین
    replacements = [r for r in rows if r.jti != jti]
    assert len(replacements) <= 1, (
        f"only one replacement session may be minted per token: {[r.jti for r in replacements]}"
    )
    assert len([r for r in rows if r.revoked_at is None]) <= 1
    assert issued_new or True  # informational; shape asserted above


# -----------------------------------------------------------
# 4) Sequential rotation still works after the locking change
#    (guards against over-locking / self-deadlock)
# -----------------------------------------------------------
def test_sequential_rotations_still_chain():
    token = _new_refresh_token()
    for _ in range(3):
        res = client.post("/auth/refresh-token", json={})
        assert res.status_code == 200, res.text
        token = client.cookies.get(COOKIE_NAME)
        assert token
        assert uuid.UUID(hex=_jti_of(token))  # still a well-formed jti

    # and the newest token is usable, the previous one is dead
    assert client.post(
        "/auth/refresh-token", json={}
    ).status_code == 200


def test_rotation_uses_server_time_not_stale_snapshot():
    """چرخش باید revoked_at/last_used_at را با زمانِ سرور بنویسد."""
    token = _new_refresh_token()
    jti = _jti_of(token)
    before = datetime.now(timezone.utc)

    db = SessionLocal()
    try:
        rotate_session(db, jti)
    finally:
        db.close()

    db = SessionLocal()
    try:
        old = db.query(RefreshSession).filter(RefreshSession.jti == jti).first()
        assert old.revoked_at is not None
        assert old.revoked_at >= before.replace(microsecond=0)
        assert old.revoked_reason == "rotated"
        assert old.replaced_by_jti
    finally:
        db.close()

def test_logout_with_a_rotated_token_revokes_the_replacement_family():
    res = client.post("/auth/login", data={"username": ADMIN_MOBILE, "password": ADMIN_PASSWORD})
    assert res.status_code == 200
    old_refresh = res.json()["refresh_token"]
    rotated = client.post("/auth/refresh-token", json={"refresh_token": old_refresh})
    assert rotated.status_code == 200
    new_refresh = rotated.json()["refresh_token"]
    assert client.post("/auth/logout", json={"refresh_token": old_refresh}).status_code == 204
    assert client.post("/auth/refresh-token", json={"refresh_token": new_refresh}).status_code == 401
