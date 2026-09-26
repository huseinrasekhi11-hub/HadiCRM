from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, status
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
from app.crud.user import get_user_by_mobile
from app.database.database import get_db
from app.models.user import User
from app.schemas.user import UserResponse

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)

# A fixed argon2 hash of a random unusable password; used only to keep
# login timing uniform for unknown mobiles. Nobody can log in with it.
_DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing-equalization-only")


@router.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="شماره موبایل یا رمز عبور اشتباه است",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ۳. کاربر غیرفعال اجازه‌ی ورود ندارد
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="این حساب کاربری غیرفعال شده است. با مدیر سیستم تماس بگیرید.",
        )

    # ۴. ثبت آخرین ورود (فیلدی که تعریف شده بود اما هرگز به‌روز نمی‌شد)
    user.last_login = datetime.now(timezone.utc)
    db.commit()

    # ۵. صدور توکن‌ها
    access_token = create_access_token(data={"sub": user.mobile})
    refresh_token = create_refresh_token(data={"sub": user.mobile})

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
    if not user_mobile:
        raise credentials_exception

    user = get_user_by_mobile(db, user_mobile)
    if not user or not user.is_active:
        raise credentials_exception

    new_access_token = create_access_token(data={"sub": user.mobile})

    return {
        "access_token": new_access_token,
        "token_type": "bearer",
        "message": "توکن با موفقیت تمدید شد",
    }
