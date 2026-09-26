from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.hashing import hash_password, verify_password
from app.auth.jwt_handler import (
    TOKEN_TYPE_REFRESH,
    create_access_token,
    create_refresh_token,
    verify_token,
)
from app.core.rate_limit import login_rate_guard, report_login_failure, report_login_success
from app.crud.user import get_user_by_mobile
from app.database.database import get_db
from app.models.user import User
from app.schemas.auth import LogoutRequest
from app.schemas.user import UserResponse
from app.services.auth_service import (
    RefreshTokenError,
    create_session_for_login,
    revoke_by_token_payload,
    rotate_session,
)

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)

# A fixed argon2 hash of a random unusable password; used only to keep
# login timing uniform for unknown mobiles. Nobody can log in with it.
_DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing-equalization-only")


@router.post("/login")
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    # ۰. کنترل نرخ ورود (brute-force / credential stuffing).
    #    پیش از این هیچ throttle‌ای وجود نداشت و حدس رمز نامحدود بود.
    login_rate_guard(request, form_data.username)

    # ۱. پیدا کردن کاربر بر اساس شماره موبایل (username در فرم لاگین)
    user = get_user_by_mobile(db, mobile=form_data.username)

    # ۲. بررسی وجود کاربر و صحت رمز عبور
    #    پیام خطا عمداً یکسان است تا مهاجم نتواند وجود/نبود شماره را
    #    از روی تفاوت پاسخ‌ها تشخیص دهد.
    #    همچنین وقتی کاربر وجود ندارد هم یک verify ساختگی اجرا می‌شود؛
    #    در غیر این صورت پاسخ «شماره‌ی موجود» به‌خاطر هزینه‌ی hashing
    #    ~۱۰۰ms کندتر از «شماره‌ی ناموجود» بود و از راه زمان‌سنجی
    #    قابل تفکیک می‌شد (account enumeration).
    if user is None:
        verify_password(form_data.password, _DUMMY_PASSWORD_HASH)
    if not user or not verify_password(form_data.password, user.password):
        report_login_failure(request, form_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="شماره موبایل یا رمز عبور اشتباه است",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ۳. کاربر غیرفعال اجازه‌ی ورود ندارد.
    #    SECURITY: پاسخ عمداً همان ۴۰۱ عمومیِ «رمز اشتباه» است؛ پیش از این
    #    یک ۴۰۳ با پیام اختصاصی برمی‌گشت و به مهاجم اجازه می‌داد شماره‌های
    #    «موجود ولی غیرفعال» را از شماره‌های نامعتبر تفکیک کند
    #    (account-state enumeration). کاربر واقعاً غیرفعال از طریق مدیر
    #    خود مطلع می‌شود، نه از طریق تفاوت پیام لاگین.
    if not user.is_active:
        report_login_failure(request, form_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="شماره موبایل یا رمز عبور اشتباه است",
            headers={"WWW-Authenticate": "Bearer"},
        )

    report_login_success(request, form_data.username)

    # ۴. ثبت آخرین ورود (فیلدی که تعریف شده بود اما هرگز به‌روز نمی‌شد)
    user.last_login = datetime.now(timezone.utc)
    db.commit()

    # ۵. صدور توکن‌ها + ثبت نشستِ سمت سرور برای توکن تمدید.
    #    از این پس هر refresh token با jti خود در جدول refresh_sessions
    #    شناخته می‌شود؛ logout/غیرفعال‌سازی/تشخیص replay می‌توانند
    #    واقعاً آن را باطل کنند (پیش از این jti هرگز ذخیره نمی‌شد و
    #    توکن سرقت‌شده تا ۷ روز قابل replay بود).
    from uuid import uuid4

    refresh_jti = uuid4().hex
    access_token = create_access_token(data={"sub": user.mobile})
    refresh_token = create_refresh_token(data={"sub": user.mobile}, jti=refresh_jti)
    create_session_for_login(db, user, refresh_jti)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/refresh-token", summary="تمدید توکن دسترسی")
def refresh_access_token(
    refresh_token: str = Body(..., embed=True),
    db: Session = Depends(get_db),
):
    """
    دریافت Refresh Token و صدور یک Access Token جدید
    بدون نیاز به نام کاربری و رمز عبور.

    اصلاحات امنیتی نسبت به نسخه‌ی قبل:
      * توکن باید واقعاً از نوع refresh باشد (نه access)؛
      * وجود و فعال‌بودن کاربر دوباره از دیتابیس بررسی می‌شود، تا
        کاربر حذف/غیرفعال‌شده نتواند نشست خود را تمدید کند؛
      * توکن در بدنه‌ی درخواست گرفته می‌شود نه در query string،
        چون query string در لاگ‌های وب‌سرور ذخیره می‌شود.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="توکن تمدید نامعتبر یا منقضی شده است",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = verify_token(refresh_token, expected_type=TOKEN_TYPE_REFRESH)
    if not payload:
        raise credentials_exception

    user_mobile = payload.get("sub")
    if not payload.get("jti") or not user_mobile:
        raise credentials_exception

    # چرخش نشست سمت سرور: توکن presented مصرف و باطل می‌شود و توکن
    # تازه‌ای در همان خانواده صادر می‌شود. استفاده‌ی مجدد از توکنِ
    # مصرف‌شده (replay/سرقت) کل خانواده را باطل می‌کند. پاسخ خطا
    # عمداً عمومی است تا وضعیت نشست‌ها به بیرون نشت نکند.
    try:
        _old_session, new_session = rotate_session(db, payload["jti"])
    except RefreshTokenError:
        raise credentials_exception

    user = get_user_by_mobile(db, user_mobile)
    if not user or not user.is_active:
        raise credentials_exception

    new_access_token = create_access_token(data={"sub": user.mobile})
    new_refresh_token = create_refresh_token(
        data={"sub": user.mobile},
        jti=new_session.jti,
    )

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "message": "توکن با موفقیت تمدید شد",
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    body: LogoutRequest,
    db: Session = Depends(get_db),
):
    """
    خروج واقعیِ سمت سرور: نشستِ توکن تمدید باطل می‌شود تا همان توکن
    حتی اگر پیش‌تر سرقت/کپی شده باشد دیگر قابل استفاده نباشد.
    پیش از این logout صرفاً کلاینت‌ساید بود (حذف از localStorage).

    پاسخ همیشه ۲۰۴ است — حتی برای توکن نامعتبر/قبلاً باطل — تا
    این اندپوینت به ابزاری برای کاوش وضعیت نشست‌ها تبدیل نشود.
    """
    payload = verify_token(body.refresh_token, expected_type=TOKEN_TYPE_REFRESH)
    if payload:
        revoke_by_token_payload(db, payload, reason="logout")
    return None
