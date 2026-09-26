from fastapi import APIRouter, Depends, HTTPException, status
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
from app.schemas.user import (
    UserCreate,
    UserUpdate,
    UserResponse,
    AssignableUserResponse,
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

    return user


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
