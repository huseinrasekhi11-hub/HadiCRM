"""
روتر محصولات
-----------------------------------------------------------
  * GET  /products/  → کاتالوگ فعال (همه‌ی کاربران احراز هویت‌شده؛
                        برای پرکردن فهرست کشویی ثبت فروش)
  * POST /products/  → افزودن کالای جدید (فقط ادمین/مدیرعامل)
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.constants.roles import Roles
from app.crud.product import create_product, get_active_products, get_product_by_name
from app.database.database import get_db
from app.models.user import User
from app.permissions.permission import require_roles
from app.schemas.product import ProductCreate, ProductResponse

router = APIRouter(
    prefix="/products",
    tags=["Products"],
)


@router.get("/", response_model=list[ProductResponse])
def list_products(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_active_products(db)


@router.post(
    "/",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(
            require_roles(
                Roles.ADMIN,
                Roles.CEO,
            )
        )
    ],
)
def create_new_product(
    product_data: ProductCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    name = (product_data.name or "").strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Product name is required.",
        )

    if get_product_by_name(db, name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Product already exists.",
        )

    return create_product(db, name)
