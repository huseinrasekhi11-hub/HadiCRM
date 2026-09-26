"""
بخش مدیریت لیدهای حذف‌شده (فقط ادمین / مدیرعامل)
-----------------------------------------------------------
این روتر «داشبورد ممیزی حذف» است:
  * لیست پرونده‌های حذف‌شده با فیلتر حذف‌کننده / مالک / تاریخ / جستجو
  * جزئیات کامل هر حذف شامل اسنپ‌شات
  * احیا (Restore) پرونده‌ی حذف‌شده

کاربران عادی هرگز این روتر را نمی‌بینند و هیچ اندپوینتی در
پاسخ‌های حذف به آن اشاره نمی‌کند.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.constants.roles import Roles
from app.crud.audit_log import create_audit_log
from app.crud.lead_deletion_audit import (
    get_deletion_audit_by_id,
    get_deletion_audits,
    restore_deleted_lead,
)
from app.database.database import get_db
from app.models.user import User
from app.permissions.permission import require_roles
from app.schemas.lead_deletion_audit import (
    LeadDeletionAuditDetailResponse,
    LeadDeletionAuditResponse,
    LeadRestoreResponse,
)

router = APIRouter(
    prefix="/deleted-leads",
    tags=["Deleted Leads (Admin)"],
    dependencies=[
        Depends(
            require_roles(
                Roles.ADMIN,
                Roles.CEO,
            )
        )
    ],
)


@router.get("/", response_model=list[LeadDeletionAuditResponse])
def list_deleted_leads(
    deleted_by_id: int | None = Query(None, description="فیلتر بر اساس کاربر حذف‌کننده"),
    owner_id: int | None = Query(None, description="فیلتر بر اساس مالک اصلی پرونده"),
    date_from: datetime | None = Query(None, description="شروع بازه‌ی زمانی حذف"),
    date_to: datetime | None = Query(None, description="پایان بازه‌ی زمانی حذف"),
    search: str | None = Query(None, description="جستجو روی نام مشتری یا موبایل"),
    include_restored: bool = Query(True, description="شامل موارد احیاشده یا بدون آن‌ها"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_deletion_audits(
        db,
        deleted_by_id=deleted_by_id,
        owner_id=owner_id,
        date_from=date_from,
        date_to=date_to,
        search=search,
        include_restored=include_restored,
        skip=skip,
        limit=limit,
    )


@router.get("/{audit_id}", response_model=LeadDeletionAuditDetailResponse)
def read_deleted_lead_detail(
    audit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    audit = get_deletion_audit_by_id(db, audit_id)
    if not audit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deletion record not found.",
        )
    return audit


@router.post("/{audit_id}/restore", response_model=LeadRestoreResponse)
def restore_deleted_lead_route(
    audit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    audit = get_deletion_audit_by_id(db, audit_id)
    if not audit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deletion record not found.",
        )

    if audit.restored_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This lead has already been restored.",
        )

    restored_lead = restore_deleted_lead(db, audit, current_user)
    if not restored_lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The underlying lead record no longer exists.",
        )

    create_audit_log(
        db,
        current_user.id,
        "restore",
        "lead",
        restored_lead.id,
        f"Deleted lead '{restored_lead.customer_name}' restored by admin.",
    )

    return {
        "status": "restored",
        "lead_id": restored_lead.id,
        "restored_at": audit.restored_at,
    }
