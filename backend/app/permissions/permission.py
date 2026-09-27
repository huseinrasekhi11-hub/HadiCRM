"""
===========================================================
لایه‌ی متمرکز سیاست‌های دسترسی (Permission Policy)
-----------------------------------------------------------
این ماژول تنها نقطه‌ی تعریف «چه کسی چه چیزی را می‌بیند» است.
پیش از این، بررسی نقش‌ها به‌صورت شرط‌های پراکنده داخل چند تابع
CRUD تکرار می‌شد و هر تغییر دامنه‌ی دسترسی نیازمند ویرایش چند
فایل بود؛ این پراکندگی در ممیزی به‌عنوان نقطه‌ی شکننده ثبت شد.

سیاست فعلی دید پرونده‌ها:
  * admin / ceo / manager / sales_manager
      → دید کامل روی همه‌ی پرونده‌ها (خواندن، ارجاع، حذف)
  * سایر نقش‌ها (از جمله sales و کارشناسان)
      → فقط پرونده‌های خودشان

سطح ممیزی مدیریتی (حذف نامحسوس، تایم‌لاین مدیریتی، نمودارها،
لاگ‌های سیستم) همچنان فقط برای admin / ceo باز است؛ مدیران
میانی به این سطح دسترسی ندارند تا قرارداد «حذف نامحسوس» حفظ شود.
===========================================================
"""
from fastapi import Depends, HTTPException, status

from app.auth.dependencies import get_current_user
from app.constants.roles import Roles
from app.models.user import User

# ---------------------------------------------------------------
# نقش‌هایی که دید نظارتی کامل روی همه‌ی پرونده‌ها دارند
# ---------------------------------------------------------------
ALL_LEADS_ROLES = (
    Roles.ADMIN,
    Roles.CEO,
    Roles.MANAGER,
    Roles.SALES_MANAGER,
)

# Roles that can be the owner of a sales lead. SALES is intentionally
# included even though it only has owner-scoped visibility.
LEAD_ASSIGNABLE_ROLES = (
    *ALL_LEADS_ROLES,
    Roles.SALES,
)

# ---------------------------------------------------------------
# نقش‌های محدود به سطح ممیزی/مدیریتی (حذف نامحسوس، نمودارها، تایم‌لاین مدیریتی)
# ---------------------------------------------------------------
ADMIN_ONLY_ROLES = (
    Roles.ADMIN,
    Roles.CEO,
)


def can_view_all_leads(current_user: User) -> bool:
    """
    آیا کاربر دید کامل روی همه‌ی پرونده‌ها دارد؟
    در غیر این صورت فقط پرونده‌های خودش را می‌بیند.
    """
    return current_user.role in ALL_LEADS_ROLES


def can_assign_any_lead(current_user: User) -> bool:
    """
    آیا کاربر می‌تواند هر پرونده‌ای را ارجاع دهد (نه فقط پرونده‌ی خودش)؟
    ارجاع یک عملیات مدیریتی است و با دید نظارتی هم‌تراز تعریف می‌شود.
    """
    return current_user.role in ALL_LEADS_ROLES


def is_admin_only_user(current_user: User) -> bool:
    """کاربر عضو سطح ممیزی/مدیریتی (ادمین/مدیرعامل) است؟"""
    return current_user.role in ADMIN_ONLY_ROLES


def require_roles(*allowed_roles):
    """
    فقط نقش‌های مشخص‌شده اجازه ورود دارند.
    """
    def checker(
        current_user: User = Depends(get_current_user),
    ):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied.",
            )
        return current_user

    return checker