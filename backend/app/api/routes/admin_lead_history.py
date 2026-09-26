"""
===========================================================
تاریخچه‌ی کامل پرونده — فقط ادمین / مدیرعامل
-----------------------------------------------------------
اندپوینت اختصاصی «تایم‌لاین مدیریتی» که کل چرخه‌ی حیات یک
پرونده را یک‌جا برمی‌گرداند:

  ایجاد، تغییر وضعیت، همه‌ی ارجاع‌ها، تاریخچه‌ی ارجاع،
 اسکالیشن‌ها، فعالیت‌ها، تغییرات پیگیری، ایجاد/اتمام وظیفه،
 فایل‌های ضمیمه، ثبت‌های تکراری و رویدادهای حذف/احیا.

این روتر به‌صورت ریشه‌ای (router-level) به نقش‌های ادمین و
مدیرعامل محدود شده است و تنها نقطه‌ای است که می‌تواند
تاریخچه‌ی پرونده‌های حذف‌شده را نیز بخواند.
===========================================================
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.constants.roles import Roles
from app.crud.lead_timeline import build_admin_timeline, get_lead_by_id_admin
from app.database.database import get_db
from app.models.user import User
from app.permissions.permission import require_roles
from app.schemas.lead_timeline import AdminLeadTimelineResponse

router = APIRouter(
    prefix="/admin/leads",
    tags=["Admin Lead History"],
    dependencies=[
        Depends(
            require_roles(
                Roles.ADMIN,
                Roles.CEO,
            )
        )
    ],
)


@router.get("/{lead_id}/timeline", response_model=AdminLeadTimelineResponse)
def read_admin_lead_timeline(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    تاریخچه‌ی کامل یک پرونده برای داشبورد مدیریتی.

    ویژگی‌ها:
      * برای پرونده‌های فعال و حذف‌شده کار می‌کند
      * رویدادها از جدیدترین به قدیمی‌ترین مرتب شده‌اند
      * جزئیات ساختاریافته‌ی ارجاع/اسکالیشن/حذف به‌صورت
        متادیتا داخل همان رویداد اصلی قرار می‌گیرد تا
        فرانت‌اند نیازی به چندین درخواست جداگانه نداشته باشد
    """
    lead = get_lead_by_id_admin(db, lead_id)
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found.",
        )

    owner = (
        db.query(User).filter(User.id == lead.owner_id).first()
        if lead.owner_id else None
    )

    events = build_admin_timeline(db, lead)

    return {
        "lead_id": lead.id,
        "customer_name": lead.customer_name,
        "mobile": lead.mobile,
        "status": lead.status,
        "is_deleted": lead.is_deleted,
        "deleted_at": lead.deleted_at,
        "owner_id": lead.owner_id,
        "owner_full_name": owner.full_name if owner else None,
        "created_at": lead.created_at,
        "duplicate_count": lead.duplicate_count or 0,
        "events": events,
    }
