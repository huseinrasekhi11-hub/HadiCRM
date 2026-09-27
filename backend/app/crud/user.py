from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.text_normalization import normalize_mobile
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
from app.auth.hashing import hash_password


# ----------------------------------
# دریافت کاربر با شماره موبایل
# ----------------------------------
def get_user_by_mobile(db: Session, mobile: str):
    """
    جست‌وجوی هویت با کلید canonical.

    پیش از این فقط برابریِ دقیقِ رشته‌ی خام مقایسه می‌شد؛ یعنی کاربری
    که شماره‌اش «09121111111» ثبت شده بود با وارد کردن «+989121111111»
    یا «۰۹۱۲۱۱۱۱۱۱۱» (ارقام فارسی) نمی‌توانست لاگین کند و ساختن
    حساب دوم با همان شماره‌ی معادل ممکن بود. حالا اول mobile_normalized
    مقایسه می‌شود؛ fallback رشته‌ی خام فقط برای رکوردهای قدیمیِ
    متناقض است (mobile_normalized=NULL پس از مهاجرت d2e6b4a8c1f5).
    """
    canonical = normalize_mobile(mobile)
    if canonical is not None:
        user = (
            db.query(User)
            .filter(User.mobile_normalized == canonical)
            .first()
        )
        if user is not None:
            return user
    return (
        db.query(User)
        .filter(User.mobile == mobile)
        .first()
    )


# ----------------------------------
# دریافت کاربر با شناسه
# ----------------------------------
def get_user(db: Session, user_id: int):
    return (
        db.query(User)
        .filter(User.id == user_id)
        .first()
    )


# ----------------------------------
# دریافت همه کاربران
# ----------------------------------
def get_users(db: Session):
    return db.query(User).all()


# ----------------------------------
# دریافت کاربران قابل‌ارجاع (فقط فعال‌ها)
# برای پرکردن لیست «ارجاع به» در ابزارهایی که همه‌ی نقش‌ها
# (نه فقط ادمین/مدیرعامل) باید بتوانند از آن استفاده کنند
# ----------------------------------
def get_assignable_users(db: Session):
    # Only sales-capable roles should ever appear in a lead-owner picker.
    # Exposing every active role (customer, accounting, warehouse, ...)
    # allowed a valid ID to be assigned to a user who has no lead scope.
    from app.permissions.permission import LEAD_ASSIGNABLE_ROLES

    return (
        db.query(User)
        .filter(
            User.is_active == True,
            User.role.in_(LEAD_ASSIGNABLE_ROLES),
        )
        .order_by(User.full_name)
        .all()
    )


# ----------------------------------
# ایجاد کاربر
# ----------------------------------
def create_user(db: Session, user: UserCreate):

    db_user = User(
        full_name=user.full_name,
        mobile=user.mobile,
        password=hash_password(user.password),
        role=user.role,
    )

    db.add(db_user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("Mobile already exists") from exc
    db.refresh(db_user)

    return db_user


# ----------------------------------
# بروزرسانی
# ----------------------------------
def update_user(
    db: Session,
    db_user: User,
    user: UserUpdate,
):

    data = user.model_dump(exclude_unset=True)

    # Serialize updates that may invalidate sessions against concurrent
    # password changes/resets and other account-state changes.
    db_user = (
        db.query(User)
        .filter(User.id == db_user.id)
        .with_for_update()
        .one()
    )
    was_active = db_user.is_active

    for key, value in data.items():
        setattr(db_user, key, value)

    if was_active and not db_user.is_active:
        # Deactivation + session generation + refresh-session revocation
        # commit together as one security transition.
        db_user.session_version += 1
        from app.services.auth_service import revoke_all_for_user

        revoke_all_for_user(
            db,
            db_user.id,
            reason="user_disabled",
            commit=False,
        )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("Mobile already exists") from exc
    db.refresh(db_user)
    return db_user


# ----------------------------------
# حذف
# ----------------------------------
def delete_user(
    db: Session,
    db_user: User,
):
    """
    غیرفعال‌سازی کاربر به‌جای حذف سخت.

    حذف سخت کاربری که مالک لید/وظیفه/فعالیت است به خطای کلید خارجی
    (HTTP 500) می‌خورد و تاریخچه‌ی ممیزی را هم از بین می‌برد. بنابراین
    کاربر غیرفعال می‌شود: دیگر نمی‌تواند وارد شود و در فهرست «ارجاع به»
    ظاهر نمی‌شود، اما تمام ارجاعات تاریخی سالم می‌مانند.
    """
    db_user = (
        db.query(User)
        .filter(User.id == db_user.id)
        .with_for_update()
        .one()
    )
    db_user.is_active = False
    db_user.session_version += 1

    # Deactivation and refresh-session revocation must commit together.
    from app.services.auth_service import revoke_all_for_user

    revoke_all_for_user(
        db,
        db_user.id,
        reason="user_disabled",
        commit=False,
    )
    db.commit()
    db.refresh(db_user)
    return db_user