"""
CRUD ممیزی حذف لید
-----------------------------------------------------------
ثبت اسنپ‌شات حذف، خواندن لیست ممیزی‌ها برای مدیر،
و احیا (Restore) پرونده‌های حذف‌شده.
"""
from datetime import datetime
from datetime import timezone

from sqlalchemy.orm import Session

from app.crud.activity import create_activity
from app.models.lead import Lead
from app.models.lead_deletion_audit import LeadDeletionAudit
from app.models.user import User
from app.schemas.activity import ActivityCreate


def _build_lead_snapshot(lead: Lead) -> dict:
    """
    ساخت اسنپ‌شات کامل JSON از پرونده در لحظه‌ی حذف.
    تاریخ‌ها به‌صورت ISO ذخیره می‌شوند تا در JSON قابل حمل باشند.
    """
    return {
        "id": lead.id,
        "customer_name": lead.customer_name,
        "mobile": lead.mobile,
        "mobile_normalized": lead.mobile_normalized,
        "customer_name_normalized": lead.customer_name_normalized,
        "duplicate_count": lead.duplicate_count,
        "source": lead.source,
        "need": lead.need,
        "status": lead.status,
        "created_by_id": lead.created_by_id,
        "owner_id": lead.owner_id,
        "last_contact_at": (
            lead.last_contact_at.isoformat() if lead.last_contact_at else None
        ),
        "next_follow_up": (
            lead.next_follow_up.isoformat() if lead.next_follow_up else None
        ),
        "last_assigned_at": (
            lead.last_assigned_at.isoformat() if lead.last_assigned_at else None
        ),
        "status_updated_at": (
            lead.status_updated_at.isoformat() if lead.status_updated_at else None
        ),
        "created_at": lead.created_at.isoformat() if lead.created_at else None,
        "updated_at": lead.updated_at.isoformat() if lead.updated_at else None,
        "loss_reason": lead.loss_reason,
        "sale_amount": lead.sale_amount,
        "sold_products": lead.sold_products,
        "invoice_number": lead.invoice_number,
        "resolution_notes": lead.resolution_notes,
        "is_escalated": lead.is_escalated,
        "score": lead.score,
    }


def record_lead_deletion(
    db: Session,
    lead: Lead,
    deleted_by: User,
    commit: bool = True,
) -> LeadDeletionAudit:
    """
    ثبت سند ممیزی حذف (اسنپ‌شات کامل) پیش از نرم‌حذفی پرونده.
    این تابع هرگز در پاسخ کاربر حذف‌کننده دیده نمی‌شود.
    """
    owner = (
        db.query(User).filter(User.id == lead.owner_id).first()
        if lead.owner_id else None
    )

    audit = LeadDeletionAudit(
        lead_id=lead.id,
        customer_name=lead.customer_name,
        mobile=lead.mobile,
        mobile_normalized=lead.mobile_normalized,
        source=lead.source,
        need=lead.need,
        previous_status=lead.status,
        loss_reason=lead.loss_reason,
        sale_amount=lead.sale_amount,
        sold_products=lead.sold_products,
        invoice_number=lead.invoice_number,
        owner_id=lead.owner_id,
        owner_full_name=owner.full_name if owner else None,
        created_by_id=lead.created_by_id,
        deleted_by_id=deleted_by.id,
        deleted_by_full_name=deleted_by.full_name,
        deleted_at=datetime.now(timezone.utc),
        snapshot=_build_lead_snapshot(lead),
    )
    db.add(audit)

    if commit:
        db.commit()
        db.refresh(audit)

    return audit


def get_deletion_audits(
    db: Session,
    deleted_by_id: int | None = None,
    owner_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    search: str | None = None,
    include_restored: bool = True,
    skip: int = 0,
    limit: int = 100,
):
    """
    لیست ممیزی‌های حذف برای داشبورد مدیر.
    فیلترها: حذف‌کننده، مالک، بازه‌ی زمانی حذف، جستجوی متنی
    روی نام مشتری/موبایل، و شامل/بدون موارد احیاشده.
    """
    query = db.query(LeadDeletionAudit)

    if deleted_by_id is not None:
        query = query.filter(LeadDeletionAudit.deleted_by_id == deleted_by_id)

    if owner_id is not None:
        query = query.filter(LeadDeletionAudit.owner_id == owner_id)

    if date_from is not None:
        query = query.filter(LeadDeletionAudit.deleted_at >= date_from)

    if date_to is not None:
        query = query.filter(LeadDeletionAudit.deleted_at <= date_to)

    if search:
        query = query.filter(
            (LeadDeletionAudit.customer_name.ilike(f"%{search}%"))
            | (LeadDeletionAudit.mobile.ilike(f"%{search}%"))
            | (LeadDeletionAudit.mobile_normalized.ilike(f"%{search}%"))
        )

    if not include_restored:
        query = query.filter(LeadDeletionAudit.restored_at.is_(None))

    return (
        query.order_by(LeadDeletionAudit.deleted_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_deletion_audit_by_id(db: Session, audit_id: int):
    return (
        db.query(LeadDeletionAudit)
        .filter(LeadDeletionAudit.id == audit_id)
        .first()
    )


def restore_deleted_lead(
    db: Session,
    audit: LeadDeletionAudit,
    current_user: User,
) -> Lead | None:
    """
    احیای پرونده‌ی حذف‌شده:
      * is_deleted پرونده پاک می‌شود و دوباره در دسترس قرار می‌گیرد
      * زمان و کاربر احیا روی سند ممیزی ثبت می‌شود
      * رویداد lead_restored در تایم‌لاین پرونده درج می‌شود

    در صورتی که پرونده فیزیکاً وجود نداشته باشد، None برمی‌گردد.
    """
    lead = db.query(Lead).filter(Lead.id == audit.lead_id).first()
    if not lead:
        return None

    lead.is_deleted = False
    lead.deleted_at = None

    audit.restored_at = datetime.now(timezone.utc)
    audit.restored_by_id = current_user.id

    create_activity(
        db,
        lead,
        current_user,
        ActivityCreate(
            activity_type="lead_restored",
            title="احیای پرونده حذف‌شده",
            description=(
                f"پرونده «{lead.customer_name}» که قبلاً حذف شده بود، "
                f"توسط {current_user.full_name} احیا شد."
            ),
        ),
        commit=False,
    )

    db.commit()
    db.refresh(lead)
    db.refresh(audit)
    return lead
