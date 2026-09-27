from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constants.roles import Roles
from app.schemas.lead import _validate_mobile


def _validate_role(value: str | None) -> str | None:
    """
    اعتبارسنجی نقش در برابر فهرست رسمی نقش‌ها.

    پیش از این هر رشته‌ای به‌عنوان role پذیرفته می‌شد؛ یک غلط تایپی
    ساده کاربری می‌ساخت که هیچ مجوزی نداشت و هیچ خطایی هم دیده نمی‌شد.
    """
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized not in Roles.ALL:
        raise ValueError(
            f"نقش نامعتبر است: «{value}». نقش‌های مجاز: {', '.join(Roles.ALL)}"
        )
    return normalized


# -----------------------------
# ایجاد کاربر
# -----------------------------
class UserCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=100)
    mobile: str = Field(min_length=1, max_length=20)
    # Minimum password policy: previously even a 1-character password was
    # accepted for brand-new accounts.
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(max_length=50)

    @field_validator("role")
    @classmethod
    def check_role(cls, v: str) -> str:
        return _validate_role(v)

    @field_validator("mobile")
    @classmethod
    def check_mobile(cls, v: str) -> str:
        return _validate_mobile(v)

    @field_validator("full_name")
    @classmethod
    def check_full_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("نام نمی‌تواند خالی باشد.")
        return v.strip()


# -----------------------------
# بروزرسانی کاربر
# -----------------------------
class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=100)
    mobile: str | None = Field(default=None, max_length=20)
    role: str | None = Field(default=None, max_length=50)
    is_active: bool | None = None

    @field_validator("mobile")
    @classmethod
    def check_mobile(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _validate_mobile(v)

    @field_validator("role")
    @classmethod
    def check_role(cls, v: str | None) -> str | None:
        return _validate_role(v)


# -----------------------------
# بازنشانی رمز توسط ادمین/مدیرعامل
# -----------------------------
class AdminPasswordResetRequest(BaseModel):
    """رمزِ جدیدی که ادمین برای کاربر تعیین می‌کند (رمزِ موقت)."""

    new_password: str = Field(min_length=8, max_length=128)


# -----------------------------
# پاسخ API
# -----------------------------
class UserResponse(BaseModel):
    id: int
    full_name: str
    mobile: str
    role: str
    is_active: bool
    is_superuser: bool

    model_config = ConfigDict(
        from_attributes=True
    )


# -----------------------------
# پاسخ سبک برای لیست «ارجاع به» — بدون موبایل و فیلدهای حساس،
# چون این اندپوینت در اختیار همه‌ی نقش‌ها (نه فقط ادمین/مدیرعامل) است
# -----------------------------
class AssignableUserResponse(BaseModel):
    id: int
    full_name: str
    role: str

    model_config = ConfigDict(
        from_attributes=True
    )
