from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
from app.auth.hashing import hash_password


# ----------------------------------
# دریافت کاربر با شماره موبایل
# ----------------------------------
def get_user_by_mobile(db: Session, mobile: str):
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
    return (
        db.query(User)
        .filter(User.is_active == True)
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
    db.commit()
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

    for key, value in data.items():
        setattr(db_user, key, value)

    db.commit()
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
    db_user.is_active = False
    db.commit()
    db.refresh(db_user)
    return db_user
