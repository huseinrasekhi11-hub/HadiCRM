from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.auth.dependencies import get_current_user
from app.models.user import User
from app.permissions.permission import require_roles
from app.constants.roles import Roles
from app.database.database import get_db

from app.crud.user import (
    get_users,
    get_user,
    create_user,
    update_user,
    delete_user,
    get_user_by_mobile,
    get_assignable_users,
)
from app.models.lead_deletion_audit import LeadDeletionAudit
from app.services.password_service import PasswordError, admin_reset_password
from app.schemas.user import (
    UserCreate,
    UserUpdate,
    UserResponse,
    AssignableUserResponse,
    AdminPasswordResetRequest,
)
def _lock_active_privileged_accounts(db: Session) -> list[User]:
    """
    Serialize destructive role changes against concurrent admin/CEO changes.
    """
    return (
        db.query(User)
        .filter(
            User.role.in_([Roles.ADMIN, Roles.CEO]),
            User.is_active.is_(True),
        )
        .with_for_update()
        .all()
    )


router = APIRouter(
    prefix="/users",
    tags=["Users"],
   dependencies=[
    Depends(
        require_roles(
            Roles.ADMIN,
            Roles.CEO,
        )
    )
]
)

# ----------------------------------------------------------------
# روتر جداگانه و بدون محدودیت نقش: فقط لیست سبک کاربران فعال را
# برمی‌گرداند (بدون موبایل/فیلدهای حساس). دلیل وجودش: طبق «چرخه‌ی
# ارجاع مجدد» در فاز ۱، خودِ کارشناسان هم می‌توانند لید را ارجاع دهند،
# اما روتر بالا (users_router) کلاً به ادمین/مدیرعامل محدود است و
# کارشناس هیچ راهی برای دیدن «به چه کسی ارجاع دهم؟» نداشت.
# ----------------------------------------------------------------
public_users_router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


@public_users_router.get("/assignable", response_model=list[AssignableUserResponse])
def read_assignable_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_assignable_users(db)


# ----------------------------------------
# دریافت همه کاربران
# ----------------------------------------
@router.get(
    "/",
    response_model=list[UserResponse],
)
def read_users(
    db: Session = Depends(get_db),
    current_user=Depends(
        require_roles(
            Roles.ADMIN,
            Roles.CEO,
            Roles.MANAGER,
        )
    ),
):
    return get_users(db)


# ----------------------------------------
# دریافت یک کاربر
# ----------------------------------------
@router.get("/{user_id}", response_model=UserResponse)
def read_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = get_user(db, user_id)

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    if (
        user.id != current_user.id
        and current_user.role not in (Roles.ADMIN, Roles.CEO, Roles.MANAGER)
    ):
        raise HTTPException(
            status_code=403,
            detail="Access denied.",
        )

    return user


@router.get("/{user_id}/deletions")
def read_user_deletions(
    user_id: int,
    include_restored: bool = Query(True, description="شامل موارد احیاشده یا بدون آن‌ها"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(Roles.ADMIN, Roles.CEO)),
):
    """
    فهرست پرونده‌های حذف‌شده‌ای که مالک اصلی‌شان این کاربر بوده —
    برای بخش «تیم فروش» پنل ادمین. (پرونده‌های حذف‌شده از جستجوی
    عمومی لیدها بیرون‌اند، پس اینجا مستقیم از ممیزی حذف خوانده می‌شود.)
    """
    if not get_user(db, user_id):
        raise HTTPException(status_code=404, detail="User not found")

    rows = (
        db.query(LeadDeletionAudit)
        .filter(LeadDeletionAudit.owner_id == user_id)
        .order_by(LeadDeletionAudit.deleted_at.desc())
        .limit(limit)
        .all()
    )
    if not include_restored:
        rows = [r for r in rows if r.restored_at is None]

    return [
        {
            "id": r.id,
            "lead_id": r.lead_id,
            "customer_name": r.customer_name,
            "mobile": r.mobile,
            "previous_status": r.previous_status,
            "owner_id": r.owner_id,
            "owner_full_name": r.owner_full_name,
            "deleted_by_id": r.deleted_by_id,
            "deleted_by_full_name": r.deleted_by_full_name,
            "deleted_at": r.deleted_at,
            "sale_amount": r.sale_amount,
            "restored_at": r.restored_at,
        }
        for r in rows
    ]


# ----------------------------------------
# ایجاد کاربر
# ----------------------------------------
@router.post(
    "/",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_new_user(
    user: UserCreate,
    db: Session = Depends(get_db),
    current_user=Depends(
        require_roles(
            Roles.ADMIN,
            Roles.CEO,
        )
    ),
):

    if get_user_by_mobile(db, user.mobile):
        raise HTTPException(
            status_code=400,
            detail="Mobile already exists",
        )

    return create_user(db, user)


# ----------------------------------------
# بازنشانی رمز عبور کاربر توسط ادمین/مدیرعامل
#
# پیش از این هیچ مسیری برای تغییر/بازنشانی رمز وجود نداشت — حتی برای
# ادمین — و رمزِ فراموش‌شده یا لو‌رفته فقط با دستکاریِ مستقیم دیتابیس
# قابل تعویض بود. بازنشانیِ خودخدمت («رمز را فراموش کرده‌ام») نیازمند
# کانالِ تحویلِ خارج از برنامه (ایمیل/پیامک) است که در این پروژه وجود
# ندارد؛ بنابراین مسیرِ پشتیبانی‌شده این است: ادمین رمزِ موقت تعیین
# می‌کند و از یک راهِ مطمئن به کاربر می‌رساند، و کاربر بعد از ورود آن را
# از طریق POST /auth/change-password عوض می‌کند.
# ----------------------------------------
@router.post("/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    body: AdminPasswordResetRequest,
    db: Session = Depends(get_db),
    current_user=Depends(
        require_roles(
            Roles.ADMIN,
            Roles.CEO,
        )
    ),
):
    db_user = get_user(db, user_id)
    if not db_user:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    # ادمین نباید از این مسیر رمزِ خودش را عوض کند: این اندپوینت به
    # دانشِ «رمز فعلی» نیاز ندارد، بنابراین برای حسابِ خودش باید از
    # /auth/change-password استفاده کند (مسیرِ سخت‌گیرانه‌تر).
    if db_user.id == current_user.id:
        raise HTTPException(
            status_code=400,
            detail=(
                "برای تغییر رمزِ حساب خود از /auth/change-password استفاده کنید "
                "(نیازمندِ رمز فعلی)."
            ),
        )

    try:
        admin_reset_password(db, db_user, body.new_password, actor=current_user)
    except PasswordError as exc:
        raise HTTPException(
            status_code=400,
            detail=exc.message,
        ) from exc

    return {
        "message": "رمز عبور کاربر بازنشانی شد و همه‌ی نشست‌های فعال او باطل شد.",
        "user_id": db_user.id,
    }


# ----------------------------------------
# بروزرسانی
# ----------------------------------------
@router.put("/{user_id}", response_model=UserResponse)
def edit_user(
    user_id: int,
    user: UserUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(
        require_roles(
            Roles.ADMIN,
            Roles.CEO,
        )
    ),
):

    db_user = get_user(db, user_id)

    if not db_user:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )
    if user.mobile:
        existing = get_user_by_mobile(db, user.mobile)
        if existing and existing.id != user_id:
            raise HTTPException(
                status_code=400,
                detail="Mobile already exists",
            )

    # همان محافظت‌های DELETE، این‌جا هم لازم است: پیش از این ادمین می‌توانست
    # با PUT خودش را غیرفعال کند یا نقش آخرین ادمین/مدیرعامل را عوض کند و
    # کل پنل مدیریتی بدون هیچ راه بازگشتی قفل می‌شد.
    deactivating = user.is_active is False
    demoting = user.role is not None and user.role not in (Roles.ADMIN, Roles.CEO)
    if db_user.id == current_user.id and (deactivating or demoting):
        raise HTTPException(
            status_code=400,
            detail="You cannot deactivate or demote your own account.",
        )
    if db_user.role in (Roles.ADMIN, Roles.CEO) and db_user.is_active and (deactivating or demoting):
        privileged = _lock_active_privileged_accounts(db)
        remaining = sum(1 for row in privileged if row.id != db_user.id)
        if remaining == 0:
            raise HTTPException(
                status_code=400,
                detail="Cannot deactivate or demote the last active admin/CEO account.",
            )
        # The locked snapshot above serializes this decision with concurrent
        # privilege changes; update_user() takes the target-user row lock.
        return update_user(db, db_user, user)

    return update_user(db, db_user, user)

            db.query(User)
            .filter(
                User.role.in_([Roles.ADMIN, Roles.CEO]),
                User.is_active.is_(True),
                User.id != db_user.id,
            )
            .count()
        )
        if remaining == 0:
            raise HTTPException(
                status_code=400,
                detail="Cannot deactivate or demote the last active admin/CEO account.",
            )

    return update_user(db, db_user, user)


# ----------------------------------------
# حذف
# ----------------------------------------
@router.delete("/{user_id}")
def remove_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(
        require_roles(
            Roles.ADMIN,
            Roles.CEO,
        )
    ),
):

    db_user = get_user(db, user_id)

    if not db_user:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    # محافظت ۱: کاربر نمی‌تواند خودش را حذف کند (قفل‌شدن از پنل).
    if db_user.id == current_user.id:
        raise HTTPException(
            status_code=400,
            detail="You cannot delete your own account.",
        )

    # محافظت ۲: آخرین ادمین/مدیرعامل فعال نباید حذف شود، وگرنه هیچ‌کس
    # دیگر به بخش‌های مدیریتی دسترسی نخواهد داشت.
    if db_user.role in (Roles.ADMIN, Roles.CEO):
        remaining = (
            db.query(User)
            .filter(
                User.role.in_([Roles.ADMIN, Roles.CEO]),
                User.is_active.is_(True),
                User.id != db_user.id,
            )
            .count()
        )
        if remaining == 0:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete the last active admin/CEO account.",
            )

    delete_user(db, db_user)

    return {
        "message": "User deactivated successfully"
    }