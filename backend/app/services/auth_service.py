"""
===========================================================
سرویس چرخه‌ی عمر نشست‌های توکن تمدید (refresh sessions)
-----------------------------------------------------------
تمام منطق سمت‌سرورِ revocation/rotation اینجا متمرکز است تا
routeها فقط جریان درخواست را ببینند:

  * create_session_for_login: ثبت نشست تازه هنگام لاگین موفق
  * rotate_session: اعتبارسنجی نشستِ jti presented و صدور نشست
    جایگزین (چرخش در هر بار استفاده)
  * تشخیص replay: استفاده از توکنِ مصرف‌شده/باطل → ابطال کل خانواده
  * revoke_session / revoke_family / revoke_all_for_user: ابطال
    صریح (logout، غیرفعال‌سازی کاربر)
  * cleanup_expired: پاک‌سازی نشست‌های منقضی قدیمی (job زمان‌بند)
===========================================================
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.logger import app_logger
from app.models.refresh_session import (
    REVOKE_REASON_LOGOUT,
    REVOKE_REASON_REUSE,
    REVOKE_REASON_ROTATED,
    REVOKE_REASON_USER_DISABLED,
    RefreshSession,
)
from app.models.user import User


class RefreshTokenError(Exception):
    """نشستِ توکن تمدید معتبر نیست (نامعتبر/منقضی/باطل/ناموجود)."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_session_for_login(
    db: Session,
    user: User,
    jti: str,
) -> RefreshSession:
    """ثبت نشست تازه برای یک لاگین موفق (خانواده‌ی جدید)."""
    session = RefreshSession(
        jti=jti,
        user_id=user.id,
        family_id=uuid4().hex,
        expires_at=_utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(session)
    db.commit()
    return session


def revoke_family(db: Session, family_id: str, reason: str) -> int:
    """ابطال همه‌ی نشست‌های فعال یک خانواده؛ تعداد نشست‌های باطل‌شده."""
    now = _utcnow()
    count = (
        db.query(RefreshSession)
        .filter(
            RefreshSession.family_id == family_id,
            RefreshSession.revoked_at.is_(None),
        )
        .update(
            {"revoked_at": now, "revoked_reason": reason},
            synchronize_session=False,
        )
    )
    db.commit()
    if count:
        app_logger.warning(
            f"[Auth] refresh family {family_id[:8]}… revoked ({reason}); "
            f"{count} session(s) invalidated."
        )
    return int(count)


def _select_session_for_rotation(db: Session, jti: str) -> RefreshSession | None:
    """
    خواندنِ نشست برای چرخش — **با قفلِ ردیف** (SELECT ... FOR UPDATE).

    این قفل نیمه‌ی اولِ رفعِ race است: دو درخواستِ هم‌زمانِ refresh با
    یک jti یکی پس از دیگری از این نقطه عبور می‌کنند، نه هر دو با هم.
    دومی تا COMMIT اولی روی همان ردیف بلاک می‌شود و بعد از آزاد شدن،
    نسخه‌ی به‌روزشده (باطل‌شده) را می‌خواند.

    نکته: در دیتابیس‌هایی که FOR UPDATE را نادیده می‌گیرند (مثل SQLite)
    این قفل بی‌اثر است؛ به همین دلیل لایه‌ی دوم (_claim_session_for_rotation)
    همیشه هم اجرا می‌شود و تصمیم نهایی را می‌گیرد.
    """
    return (
        db.query(RefreshSession)
        .filter(RefreshSession.jti == jti)
        .with_for_update()
        .first()
    )


def _claim_session_for_rotation(
    db: Session,
    session: RefreshSession,
    new_jti: str,
    now: datetime,
) -> bool:
    """
    لایه‌ی دومِ ضدرقابت: ابطالِ شرطی و اتمیکِ نشستِ فعلی.

    به‌جای «نوشتنِ revoked_at روی شیء و امید به این‌که هنوز کسی آن را
    مصرف نکرده باشد»، انتقالِ وضعیت با یک UPDATE شرطی انجام می‌شود:

        UPDATE refresh_sessions SET revoked_at=... 
         WHERE id = :id AND revoked_at IS NULL

    و تنها در صورتی موفق تلقی می‌شود که دقیقاً یک ردیف تحت‌تأثیر قرار
    گرفته باشد. اگر ردیفی به‌روز نشود (۰ ردیف) یعنی تراکنشِ دیگری در
    همان لحظه این توکن را چرخانده/باطل کرده است — یعنی این درخواست
    بازنده‌ی race است، حتی اگر SELECT قبلی (اسنپ‌شاتِ کهنه) هنوز
    «فعال» را نشان می‌داد (TOCTOU کلاسیک).

    برگشتی: True اگر این تراکنش مالکِ چرخش شد، False اگر رقابت را باخت.
    """
    claimed = (
        db.query(RefreshSession)
        .filter(
            RefreshSession.id == session.id,
            RefreshSession.revoked_at.is_(None),
        )
        .update(
            {
                "revoked_at": now,
                "revoked_reason": REVOKE_REASON_ROTATED,
                "replaced_by_jti": new_jti,
                "last_used_at": now,
            },
            synchronize_session=False,
        )
    )
    return claimed == 1


def rotate_session(db: Session, jti: str) -> tuple[RefreshSession, RefreshSession]:
    """
    اعتبارسنجی نشستِ jti و چرخش آن — به‌صورت اتمیک در برابرِ درخواست‌های
    هم‌زمان (single-use تضمین‌شده در سطح دیتابیس، نه فقط در سطح پایتون).

    خروجی: (old_session, new_session) — old_session همین‌جا باطل و
    new_session جایگزین آن ثبت می‌شود. خطاها با RefreshTokenError:

      * not_found: jti در DB نیست (توکن قبل از استقرارِ این مکانیزم
        صادر شده یا ساختگی است)
      * reused: توکنِ قبلاً مصرف‌شده دوباره ارائه شده → replay قطعی؛
        کل خانواده باطل می‌شود (هم توکن دزد از کار می‌افتد هم توکنی
        که جایگزینش شده بود؛ کاربر واقعی با لاگین مجدد بازیابی می‌کند)
      * revoked: نشست صریحاً باطل شده (logout/غیرفعال‌سازی)
      * expired: انقضای سمت سرور (مستقل از exp داخل JWT)

    ایمنیِ هم‌زمانی (concurrency):
        پیش از این ترتیبِ کار چنین بود:
            SELECT ردیف → بررسیِ وضعیت در پایتون → ساخت نشست جدید → COMMIT
        یعنی دو درخواستِ هم‌زمان با یک refresh token هر دو «فعال» می‌دیدند
        و هر دو نشستِ تازه صادر می‌کردند (TOCTOU): توکنِ یک‌بار‌مصرف عملاً
        دو بار مصرف می‌شد و مهاجمی که توکن را در اختیار داشت می‌توانست هم‌زمان
        با کلاینتِ واقعی آن را چرخش دهد. حالا:
            ۱. ردیف با FOR UPDATE قفل می‌شود (در همان تراکنش)،
            ۲. انتقالِ وضعیت با UPDATE شرطیِ WHERE revoked_at IS NULL و
               بررسیِ تعداد ردیف‌های تحت‌تأثیر انجام می‌شود،
            ۳. نشستِ جدید فقط در صورت موفقیتِ آن claim درج می‌شود.
        بنابراین در هر لحظه حداکثر یک تراکنش می‌تواند یک jti را مصرف کند.
    """
    session = _select_session_for_rotation(db, jti)
    if session is None:
        raise RefreshTokenError("not_found")

    now = _utcnow()
    family_id = session.family_id

    if session.is_revoked:
        if session.revoked_reason == REVOKE_REASON_ROTATED:
            # این توکن یک‌بار مصرف و جایگزین شده؛ ارائه‌ی دوباره‌ی آن
            # یعنی replay (یا کلاینتِ قدیمی که توکن چرخش‌یافته را
            # ذخیره نکرده). در هر دو حالت امن‌ترین واکنش، ابطال کل
            # خانواده است.
            revoke_family(db, family_id, REVOKE_REASON_REUSE)
            raise RefreshTokenError("reused")
        raise RefreshTokenError("revoked")

    if session.expires_at <= now:
        session.revoked_at = now
        session.revoked_reason = "expired"
        db.commit()
        raise RefreshTokenError("expired")

    user = db.query(User).filter(User.id == session.user_id).first()
    if user is None or not user.is_active:
        revoke_family(db, family_id, REVOKE_REASON_USER_DISABLED)
        raise RefreshTokenError("user_inactive")

    new_jti = uuid4().hex

    # اتمیک: اگر تراکنشِ دیگری هم‌زمان همین jti را مصرف کرده باشد، این
    # UPDATE صفر ردیف را تحت‌تأثیر قرار می‌دهد و ما بازنده‌ایم.
    if not _claim_session_for_rotation(db, session, new_jti, now):
        db.rollback()
        # همان واکنشِ تشخیصِ replay: دو مصرفِ هم‌زمان از یک توکنِ
        # یک‌بار‌مصرف، از دید سرور تفاوتی با replay ندارد — کل خانواده
        # باطل می‌شود تا هیچ‌کدام از دو نشستِ رقیب زنده نماند.
        revoke_family(db, family_id, REVOKE_REASON_REUSE)
        app_logger.warning(
            f"[Auth] concurrent rotation detected for jti {jti[:8]}…; "
            f"family {family_id[:8]}… revoked ({REVOKE_REASON_REUSE})."
        )
        raise RefreshTokenError("reused")

    new_session = RefreshSession(
        jti=new_jti,
        user_id=session.user_id,
        family_id=family_id,
        expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(new_session)

    db.commit()
    db.refresh(new_session)
    return session, new_session


def revoke_session(db: Session, jti: str, reason: str = REVOKE_REASON_LOGOUT) -> bool:
    """ابطال یک نشست مشخص (logout). توکن نامعتبر/قبلاً باطل → False بی‌صدا."""
    session = (
        db.query(RefreshSession)
        .filter(RefreshSession.jti == jti, RefreshSession.revoked_at.is_(None))
        .first()
    )
    if session is None:
        return False
    session.revoked_at = _utcnow()
    session.revoked_reason = reason
    db.commit()
    return True


def revoke_by_token_payload(db: Session, payload: dict, reason: str) -> bool:
    """ابطال بر اساس payload یک توکن تمدیدِ از قبل verify‌شده."""
    jti = payload.get("jti")
    if not jti:
        return False
    return revoke_session(db, jti, reason=reason)


def revoke_all_for_user(db: Session, user_id: int, reason: str = REVOKE_REASON_USER_DISABLED) -> int:
    """ابطال همه‌ی نشست‌های فعال یک کاربر (غیرفعال‌سازی/حذف)."""
    now = _utcnow()
    count = (
        db.query(RefreshSession)
        .filter(
            RefreshSession.user_id == user_id,
            RefreshSession.revoked_at.is_(None),
        )
        .update(
            {"revoked_at": now, "revoked_reason": reason},
            synchronize_session=False,
        )
    )
    db.commit()
    if count:
        app_logger.info(
            f"[Auth] all refresh sessions revoked for user {user_id} ({reason}): {count}."
        )
    return int(count)


def cleanup_expired(db: Session, retention_days: int | None = None) -> int:
    """
    حذف فیزیکی نشست‌های منقضی/باطلِ قدیمی تا جدول رشد بی‌پایان نکند.
    رکوردها تا retention_DAYS روز پس از انقضا نگه داشته می‌شوند
    (برای ردیابی ممیزی)، بعد حذف می‌شوند.
    """
    if retention_days is None:
        retention_days = settings.REFRESH_TOKEN_EXPIRE_DAYS
    cutoff = _utcnow() - timedelta(days=retention_days)
    count = (
        db.query(RefreshSession)
        .filter(RefreshSession.expires_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    return int(count)
