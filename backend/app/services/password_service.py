"""
===========================================================
سرویس تغییر/بازنشانی رمز عبور
-----------------------------------------------------------
پیش از این هیچ اندپوینتی برای تغییر یا بازنشانی رمز وجود نداشت — نه برای
کاربر عادی و نه برای ادمین؛ یعنی رمزِ لو‌رفته/فراموش‌شده تنها با دستکاریِ
مستقیمِ دیتابیس قابل تعویض بود (گزارش ممیزی: «MEDIUM — no password
change/reset system»).

قوانینِ پیاده‌سازی:
  * تغییر رمز نیازمندِ «رمز فعلی» است (مهاجمی که نشست或者 توکنِ دسترسی
    دزدیده باشد، نمی‌تواند حساب را با تغییرِ رمز تصاحب کند)؛
  * رمز جدید با سیاستِ حداقل طول بررسی می‌شود و نباید همان رمزِ قبلی باشد؛
  * بعد از تغییر/بازنشانی، همه‌ی نشست‌های توکن تمدیدِ آن کاربر باطل
    می‌شود (نشستِ جاریِ درخواست‌کننده در صورتِ ارائه‌ی jti حفظ می‌شود)؛
  * رویداد در audit_log ثبت می‌شود؛
  * حدسِ «رمز فعلی» هم مشمولِ بودجه‌ی محدودسازیِ مشترک است
    (app/core/rate_limit.py).
===========================================================
"""
from sqlalchemy.orm import Session

from app.auth.hashing import hash_password, verify_password
from app.core.logger import app_logger
from app.models.refresh_session import REVOKE_REASON_PASSWORD_CHANGE
from app.models.user import User
from app.services.auth_service import revoke_all_for_user

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


class PasswordError(Exception):
    """خطایِ قابل‌نمایش به کاربر در جریانِ تغییر/بازنشانیِ رمز."""

    def __init__(self, reason: str, message: str | None = None):
        self.reason = reason
        self.message = message or "رمز عبور معتبر نیست."
        super().__init__(reason)


def validate_password_policy(new_password: str) -> str:
    """
    اعمالِ همان سیاستی که در ساخت کاربر (UserCreate) برقرار است.
    خروجی: رمزِ پذیرفته‌شده (trim نشده — فضای خالیِ ابتدایی/انتهایی
    عمداً حفظ می‌شود، فقط طولِ واقعی بررسی می‌شود).
    """
    if not isinstance(new_password, str) or len(new_password) < MIN_PASSWORD_LENGTH:
        raise PasswordError(
            "too_short",
            f"رمز عبور باید حداقل {MIN_PASSWORD_LENGTH} کاراکتر باشد.",
        )
    if len(new_password) > MAX_PASSWORD_LENGTH:
        raise PasswordError(
            "too_long",
            f"رمز عبور نمی‌تواند بیش از {MAX_PASSWORD_LENGTH} کاراکتر باشد.",
        )
    if new_password.strip() == "":
        raise PasswordError("blank", "رمز عبور نمی‌تواند فقط فاصله باشد.")
    return new_password


def change_password(
    db: Session,
    user: User,
    current_password: str,
    new_password: str,
    keep_jti: str | None = None,
) -> None:
    """
    تغییر رمز توسط خودِ کاربر (نیازمندِ رمز فعلی).

    keep_jti: نشستِ توکن تمدیدی که باید زنده بماند (نشستِ همین دستگاه)؛
    بقیه‌ی نشست‌ها باطل می‌شوند تا هر دستگاه/توکنِ دیگری که با رمزِ قدیمی
    بالا آمده از کار بیفتد.
    """
    if not verify_password(current_password, user.password):
        raise PasswordError(
            "invalid_current_password", "رمز عبور فعلی اشتباه است."
        )

    new_password = validate_password_policy(new_password)
    if verify_password(new_password, user.password):
        raise PasswordError(
            "reused_password", "رمز جدید باید با رمز فعلی متفاوت باشد."
        )

    user.password = hash_password(new_password)
    db.commit()
    db.refresh(user)

    revoked = revoke_all_for_user(
        db,
        user.id,
        reason=REVOKE_REASON_PASSWORD_CHANGE,
        except_jti=keep_jti,
    )
    _audit_password_change(db, user, actor=user, revoked=revoked, by_admin=False)
    app_logger.info(
        f"[Auth] password changed for user {user.id}; "
        f"{revoked} other session(s) revoked."
    )


def admin_reset_password(
    db: Session,
    target_user: User,
    new_password: str,
    actor: User,
) -> None:
    """
    بازنشانی رمز توسط ادمین/مدیرعامل (بدون نیاز به رمز فعلیِ کاربر).

    چرا «reset» و نه «change»؟ چون بیرون از برنامه هیچ کانالِ تحویلِ
    مطمئنی (ایمیل/پیامک) برای ارسالِ لینکِ بازنشانی وجود ندارد؛ بنابراین
    بازنشانیِ خودخدمتِ «رمز فراموش‌شده» در این نسخه پیاده‌سازی نشده و
    مسیرِ پشتیبانی‌شده «ادمین رمزِ موقت تعیین می‌کند و از راهِ مطمئن به
    کاربر می‌رساند» است.
    """
    new_password = validate_password_policy(new_password)

    target_user.password = hash_password(new_password)
    db.commit()
    db.refresh(target_user)

    # بازنشانیِ کامل: هیچ نشستی حفظ نمی‌شود (حتی نشستِ خودِ ادمین در
    # صورتِ اشتباه‌گرفتنِ کاربر هدف — چون ادمین اینجا روی «دیگری» عمل می‌کند)
    revoked = revoke_all_for_user(
        db, target_user.id, reason=REVOKE_REASON_PASSWORD_CHANGE
    )
    _audit_password_change(db, target_user, actor=actor, revoked=revoked, by_admin=True)
    app_logger.warning(
        f"[Auth] password reset for user {target_user.id} by admin {actor.id}; "
        f"{revoked} session(s) revoked."
    )


def _audit_password_change(
    db: Session,
    user: User,
    *,
    actor: User,
    revoked: int,
    by_admin: bool,
) -> None:
    """ثبت رویداد در لاگ ممیزی؛ شکستِ ثبت نباید خودِ عملیات را خراب کند."""
    from app.crud.audit_log import create_audit_log

    action = "reset_password" if by_admin else "change_password"
    create_audit_log(
        db,
        user_id=actor.id,
        action=action,
        entity="user",
        entity_id=user.id,
        description=(
            f"{'بازنشانی' if by_admin else 'تغییر'} رمز عبور کاربر "
            f"{user.id} ({user.mobile}); {revoked} نشست باطل شد."
        ),
    )
