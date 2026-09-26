"""
ساخت و اعتبارسنجی توکن‌های JWT.

نکته‌ی امنیتی: توکن دسترسی و توکن تازه‌سازی با همان کلید امضا می‌شوند،
بنابراین بدون تفکیک نوع، یک refresh token هم می‌توانست به‌عنوان bearer
در همه‌ی اندپوینت‌ها استفاده شود. برای رفع این مشکل ادعای «type» به
هر توکن اضافه و هنگام اعتبارسنجی بررسی می‌شود.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from jwt import PyJWTError

from app.config.settings import settings

TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"

# Fail fast instead of silently accepting a misconfigured ALGORITHM env
# (e.g. "none" or an asymmetric key with an HMAC algorithm).
_ALLOWED_ALGORITHMS = {"HS256", "HS384", "HS512"}
if settings.ALGORITHM not in _ALLOWED_ALGORITHMS:
    raise RuntimeError(
        f"Unsupported JWT ALGORITHM {settings.ALGORITHM!r}; "
        f"allowed: {sorted(_ALLOWED_ALGORITHMS)}"
    )


def create_access_token(data: dict):
    """ساخت Access Token"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode.update(
        {
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "jti": uuid4().hex,
            "type": TOKEN_TYPE_ACCESS,
        }
    )
    return jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def create_refresh_token(data: dict, jti: str | None = None):
    """
    تولید توکن تمدید نشست (Refresh Token).

    jti اختیاری است: وقتی نشستِ سمت سرور (refresh_sessions) از قبل با
    یک jti مشخص ثبت شده، همان jti داخل توکن قرار می‌گیرد تا JWT و
    رکورد DB به یکدیگر گره بخورند (چرخش/ابطال سمت سرور).
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    to_encode.update(
        {
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "jti": jti or uuid4().hex,
            "type": TOKEN_TYPE_REFRESH,
        }
    )
    return jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def verify_token(token: str, expected_type: str | None = TOKEN_TYPE_ACCESS):
    """
    اعتبارسنجی Token.

    اگر expected_type داده شود، توکنی که نوع دیگری دارد رد می‌شود.
    توکن‌های قدیمیِ بدون ادعای «type» برای دوره‌ی گذار به‌عنوان
    access پذیرفته می‌شوند تا نشست‌های باز کاربران قطع نشود.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
    except PyJWTError:
        return None

    if expected_type is not None:
        token_type = payload.get("type", TOKEN_TYPE_ACCESS)
        if token_type != expected_type:
            return None

    return payload
