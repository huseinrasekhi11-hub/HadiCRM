from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.auth.cookies import clear_refresh_cookie, set_refresh_cookie
from app.auth.csrf import enforce_csrf_for_browser_request, enforce_csrf_for_cookie_auth
from app.auth.dependencies import get_current_user
from app.auth.hashing import hash_password, verify_password
from app.auth.jwt_handler import (
    TOKEN_TYPE_REFRESH,
    create_access_token,
    create_refresh_token,
    verify_token,
)
from app.config.settings import settings
from app.core.rate_limit import (
    login_rate_guard,
    password_change_guard,
    report_login_failure,
    report_login_success,
    report_password_change_failure,
    report_password_change_success,
)
from app.crud.user import get_user_by_mobile
from app.database.database import get_db
from app.models.user import User
from app.schemas.auth import ChangePasswordRequest, LogoutRequest
from app.schemas.user import UserResponse
from app.services.auth_service import (
    RefreshTokenError,
    create_session_for_login,
    revoke_by_token_payload,
    rotate_session,
)
from app.services.password_service import PasswordError, change_password

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)

# A fixed argon2 hash of a random unusable password; used only to keep
# login timing uniform for unknown mobiles. Nobody can log in with it.
_DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing-equalization-only")


def _refresh_token_from_request(request: Request, body_token: str | None) -> tuple[str | None, bool]:
    """
    توکن تمدید را از بدنه (کلاینت‌های قدیمی/غیرمرورگری) یا از کوکیِ
    HttpOnly (مسیرِ پیش‌فرضِ مرورگر) می‌خواند.

    خروجی: (توکن یا None، آیا از کوکی آمده است)
    """
    if body_token:
        return body_token, False
    cookie_token = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if cookie_token:
        return cookie_token, True
    return None, False


@router.post("/login")
def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    enforce_csrf_for_browser_request(request)

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
    refresh_jti = uuid4().hex
    access_token = create_access_token(
        data={"sub": user.mobile, "sv": user.session_version}
    )
    refresh_token = create_refresh_token(data={"sub": user.mobile}, jti=refresh_jti)
    create_session_for_login(db, user, refresh_jti)

    # توکن تمدید فقط در کوکیِ HttpOnly نصب می‌شود. بازگرداندنِ آن در
    # JSON عملاً مزیت HttpOnly را خنثی می‌کند: هر اسکریپتِ XSS می‌تواند
    # پاسخ login/refresh را بخواند و refresh token را بدزدد.
    set_refresh_cookie(response, refresh_token, request)

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/refresh-token", summary="تمدید توکن دسترسی")
def refresh_access_token(
    request: Request,
    response: Response,
    refresh_token: str | None = Body(default=None, embed=True),
    db: Session = Depends(get_db),
):
    """
    دریافت Refresh Token و صدور یک Access Token جدید
    بدون نیاز به نام کاربری و رمز عبور.

    توکن تمدید از بدنه (سازگاری با کلاینت‌های قدیمی/غیرمرورگری) یا از
    کوکیِ HttpOnly خوانده می‌شود؛ در حالتِ دوم بررسیِ CSRF هم اعمال
    می‌شود (app/auth/csrf.py).

    اصلاحات امنیتی نسبت به نسخه‌ی قبل:
      * توکن باید واقعاً از نوع refresh باشد (نه access)؛
      * وجود و فعال‌بودن کاربر دوباره از دیتابیس بررسی می‌شود، تا
        کاربر حذف/غیرفعال‌شده نتواند نشست خود را تمدید کند؛
      * توکن در بدنه‌ی درخواست گرفته می‌شود نه در query string،
        چون query string در لاگ‌های وب‌سرور ذخیره می‌شود؛
      * چرخشِ نشست به‌صورت اتمیک (قفلِ ردیف + UPDATE شرطی) انجام
        می‌شود تا دو درخواستِ هم‌زمان نتوانند یک توکن را دوبار خرج کنند.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="توکن تمدید نامعتبر یا منقضی شده است",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token, from_cookie = _refresh_token_from_request(request, refresh_token)
    if not token:
        raise credentials_exception
    if from_cookie:
        enforce_csrf_for_cookie_auth(request)

    payload = verify_token(token, expected_type=TOKEN_TYPE_REFRESH)
    if not payload:
        clear_refresh_cookie(response, request)
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
        clear_refresh_cookie(response, request)
        raise credentials_exception

    # Bind the refresh session to the server-side user identity rather
    # than the historical mobile string embedded in the JWT. This keeps a
    # valid session usable after an administrator changes the mobile number.
    user = db.query(User).filter(User.id == new_session.user_id).first()
    if not user or not user.is_active:
        clear_refresh_cookie(response, request)
        raise credentials_exception

    new_access_token = create_access_token(
        data={"sub": user.mobile, "sv": user.session_version}
    )
    new_refresh_token = create_refresh_token(
        data={"sub": user.mobile},
        jti=new_session.jti,
    )
    set_refresh_cookie(response, new_refresh_token, request)

    # refresh token عمداً در پاسخ JSON بازگردانده نمی‌شود؛ فقط Set-Cookie
    # آن را در اختیار مرورگر قرار می‌دهد، تا XSS نتواند نشستِ بلندمدت را
    # مستقیماً از پاسخ شبکه استخراج کند.
    return {
        "access_token": new_access_token,
        "token_type": "bearer",
        "message": "توکن با موفقیت تمدید شد",
    }


@router.post("/change-password", summary="تغییر رمز عبور توسط خود کاربر")
def change_my_password(
    request: Request,
    response: Response,
    body: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    تغییر رمزِ حسابِ لاگین‌شده.

    نیازمندِ «رمز فعلی» است تا نشست/توکنِ دزدیده‌شده نتواند حساب را با
    تغییرِ رمز تصاحب کند. بعد از تغییر، همه‌ی نشست‌های دیگرِ این کاربر
    (دستگاه‌ها و توکن‌های تمدیدِ صادر‌شده) باطل می‌شوند؛ نشستِ همین
    درخواست در صورتِ ارائه‌ی توکن تمدید (کوکی یا بدنه) حفظ می‌شود.
    """
    # حدسِ «رمز فعلی» هم باید محدود باشد؛ در غیر این صورت این اندپوینت
    # یک مسیرِ نامحدود برای brute-forceِ رمز روی یک نشستِ دزدیده‌شده بود.
    password_change_guard(request, current_user.mobile)

    keep_jti = None
    body_token = body.refresh_token
    token, _from_cookie = _refresh_token_from_request(request, body_token)
    if token:
        payload = verify_token(token, expected_type=TOKEN_TYPE_REFRESH)
        if payload and payload.get("jti"):
            keep_jti = payload["jti"]

    try:
        change_password(
            db,
            current_user,
            current_password=body.current_password,
            new_password=body.new_password,
            keep_jti=keep_jti,
        )
    except PasswordError as exc:
        report_password_change_failure(request, current_user.mobile)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.message,
        ) from exc

    report_password_change_success(request, current_user.mobile)

    # session_version invalidates the old bearer token immediately. When
    # the current refresh session is kept, issue a replacement access token
    # for this browser tab; the refresh credential remains HttpOnly-only.
    if keep_jti is None:
        clear_refresh_cookie(response, request)

    fresh_access_token = (
        create_access_token(
            data={"sub": current_user.mobile, "sv": current_user.session_version}
        )
        if keep_jti is not None
        else None
    )

    return {
        "message": "رمز عبور با موفقیت تغییر کرد.",
        "current_session_kept": keep_jti is not None,
        "access_token": fresh_access_token,
        "token_type": "bearer" if fresh_access_token else None,
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    body: LogoutRequest | None = None,
    db: Session = Depends(get_db),
):
    """
    خروج واقعیِ سمت سرور: نشستِ توکن تمدید باطل می‌شود تا همان توکن
    حتی اگر پیش‌تر سرقت/کپی شده باشد دیگر قابل استفاده نباشد.
    پیش از این logout صرفاً کلاینت‌ساید بود (حذف از localStorage).

    پاسخ همیشه ۲۰۴ است — حتی برای توکن نامعتبر/قبلاً باطل — تا
    این اندپوینت به ابزاری برای کاوش وضعیت نشست‌ها تبدیل نشود.
    """
    body_token = body.refresh_token if body else None
    token, from_cookie = _refresh_token_from_request(request, body_token)
    if token and from_cookie:
        enforce_csrf_for_cookie_auth(request)
    if token:
        payload = verify_token(token, expected_type=TOKEN_TYPE_REFRESH)
        if payload:
            revoke_by_token_payload(db, payload, reason="logout")

    clear_refresh_cookie(response, request)
    return None