from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    mobile: str
    password: str


class ChangePasswordRequest(BaseModel):
    """تغییر رمز توسط خودِ کاربر؛ رمزِ فعلی الزامی است."""

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
    # نشستِ توکن تمدیدی که باید بعد از تغییر رمز زنده بماند (همین دستگاه).
    # در استقرارِ مبتنی بر کوکی نیازی به ارسالِ آن نیست (از کوکی خوانده می‌شود).
    refresh_token: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LogoutRequest(BaseModel):
    """
    بدنه‌ی درخواست خروج — توکن تمدیدی که باید سمت سرور باطل شود.

    اختیاری است: مرورگر توکن را در کوکیِ HttpOnly دارد و نیازی به
    فرستادنِ بدنه نیست (در آن صورت توکن از کوکی خوانده می‌شود).
    """

    refresh_token: str | None = None
