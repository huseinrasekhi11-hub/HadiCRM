"""
===========================================================
تایم‌لاین یکپارچه‌ی مدیریتی (Complete Admin Lead History)
-----------------------------------------------------------
این ماژول «کل چرخه‌ی حیات» یک پرونده را از منابع مختلف
بازسازی می‌کند:

  * activities           → ایجاد، تغییر وضعیت، ارجاع، وظایف،
                           پیگیری‌ها، کشف تکراری، حذف، احیا
  * assignment_history   → جزئیات ساختاریافته‌ی هر ارجاع
                           (ارجاع‌دهنده / ارجاع‌گیرنده / یادداشت)
  * lead_escalations     → ارجاع‌های اضطراری با دلیل
  * attachments          → فایل‌های بارگذاری‌شده
  * lead_deletion_audits → رویدادهای حذف و احیا با اسنپ‌شات

استراتژی ادغام:
  هر ارجاع/اسکالیشن/حذف، هم‌زمان یک Activity هم تولید می‌کند.
  برای جلوگیری از رویداد تکراری، رکورد ساختاریافته‌ی متناظر
  (از روی نزدیکی زمانی) به‌صورت متادیتا به رویداد Activity
  متصل می‌شود؛ اگر رکوردی همتا نداشت (داده‌های قدیمی)، به‌صورت
  یک رویداد مستقل منتشر می‌شود تا هیچ بخشی از تاریخچه گم نشود.

نکته‌ی دسترسی: این ماژول فقط توسط روتر مخصوص ادمین/مدیرعامل
فراخوانی می‌شود؛ فیلتر is_deleted عمداً در بارگذاری پرونده
نادیده گرفته می‌شود تا تاریخچه‌ی پرونده‌های حذف‌شده نیز کامل
قابل مشاهده بماند.
===========================================================
"""
from datetime import timezone

from sqlalchemy.orm import Session

from app.models.activity import Activity
from app.models.assignment_history import AssignmentHistory
from app.models.attachment import Attachment
from app.models.lead import Lead
from app.models.lead_deletion_audit import LeadDeletionAudit
from app.models.lead_escalation import LeadEscalation
from app.models.user import User

# حداکثر فاصله‌ی زمانی (ثانیه) برای تطبیق یک رویداد سیستمی با رکورد ساختاریافته‌ی آن
MATCH_TOLERANCE_SECONDS = 10


def _aware(dt):
    """
    تبدیل امن تاریخ به timezone-aware.
    رکوردهای قدیمی ممکن است naive ذخیره شده باشند؛ برای مقایسه‌ی
    امن، آن‌ها را UTC فرض می‌کنیم.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def get_lead_by_id_admin(db: Session, lead_id: int) -> Lead | None:
    """
    بارگذاری پرونده برای دید مدیریتی.
    برخلاف get_my_lead_by_id:
      * فیلتر is_deleted ندارد (تاریخچه‌ی پرونده‌ی حذف‌شده هم دیده می‌شود)
      * فیلتر مالکیت ندارد (فقط در روتر با نقش ادمین/مدیرعامل صدا زده می‌شود)
    """
    return (
        db.query(Lead)
        .filter(Lead.id == lead_id)
        .first()
    )


def _closest_match(rows, target_time, time_attr: str, consumed_ids: set):
    """
    نزدیک‌ترین رکورد (از نظر زمانی) به رویداد مرجع را پیدا می‌کند،
    به‌شرط آن‌که قبلاً مصرف نشده باشد و داخل بازه‌ی تحمل باشد.
    """
    if target_time is None:
        return None

    best = None
    best_delta = None

    for row in rows:
        if row.id in consumed_ids:
            continue

        row_time = _aware(getattr(row, time_attr))
        if row_time is None:
            continue

        delta = abs((row_time - target_time).total_seconds())
        if delta <= MATCH_TOLERANCE_SECONDS and (best_delta is None or delta < best_delta):
            best = row
            best_delta = delta

    return best


def build_admin_timeline(db: Session, lead: Lead) -> list[dict]:
    """
    ساخت جریان رویدادهای یکپارچه برای یک پرونده (فعال یا حذف‌شده).
    خروجی: لیستی از دیکشنری‌ها، مرتب‌شده از جدیدترین به قدیمی‌ترین.
    """
    # ----------------------------------------------------------
    # بارگذاری کامل همه‌ی منابع تاریخچه
    # ----------------------------------------------------------
    activities = (
        db.query(Activity)
        .filter(Activity.lead_id == lead.id)
        .order_by(Activity.created_at.asc())
        .all()
    )

    assignments = (
        db.query(AssignmentHistory)
        .filter(AssignmentHistory.lead_id == lead.id)
        .order_by(AssignmentHistory.assigned_at.asc())
        .all()
    )

    escalations = (
        db.query(LeadEscalation)
        .filter(LeadEscalation.lead_id == lead.id)
        .order_by(LeadEscalation.created_at.asc())
        .all()
    )

    attachments = (
        db.query(Attachment)
        .filter(Attachment.lead_id == lead.id)
        .order_by(Attachment.created_at.asc())
        .all()
    )

    deletion_audits = (
        db.query(LeadDeletionAudit)
        .filter(LeadDeletionAudit.lead_id == lead.id)
        .order_by(LeadDeletionAudit.deleted_at.asc())
        .all()
    )

    # ----------------------------------------------------------
    # جمع‌آوری شناسه‌ی کاربران درگیر برای یک‌بار واکشی نام‌ها
    # ----------------------------------------------------------
    user_ids: set[int] = set()
    for activity in activities:
        user_ids.add(activity.user_id)
    for history in assignments:
        user_ids.add(history.assigned_by_id)
        user_ids.add(history.assigned_to_id)
    for escalation in escalations:
        user_ids.add(escalation.escalated_from_id)
        user_ids.add(escalation.escalated_to_id)
    for attachment in attachments:
        user_ids.add(attachment.uploaded_by_id)
    for audit in deletion_audits:
        user_ids.add(audit.deleted_by_id)
        if audit.restored_by_id is not None:
            user_ids.add(audit.restored_by_id)
    user_ids.discard(None)

    user_names: dict[int, str] = {}
    if user_ids:
        rows = (
            db.query(User.id, User.full_name)
            .filter(User.id.in_(list(user_ids)))
            .all()
        )
        user_names = {user_id: full_name for user_id, full_name in rows}

    events: list[dict] = []
    consumed_assignments: set[int] = set()
    consumed_escalations: set[int] = set()
    consumed_deletions: set[int] = set()
    consumed_restorations: set[int] = set()

    # ----------------------------------------------------------
    # ۱) ستون فقرات: فعالیت‌ها + غنی‌سازی با رکوردهای ساختاریافته
    # ----------------------------------------------------------
    for activity in activities:
        occurred_at = _aware(activity.created_at)
        metadata: dict = {}

        if activity.activity_type in ("lead_created", "lead_assigned", "escalated"):
            history = _closest_match(
                assignments,
                occurred_at,
                "assigned_at",
                consumed_assignments,
            )
            if history is not None:
                consumed_assignments.add(history.id)
                metadata["assignment"] = {
                    "assignment_id": history.id,
                    "assigned_by_id": history.assigned_by_id,
                    "assigned_by_name": user_names.get(history.assigned_by_id),
                    "assigned_to_id": history.assigned_to_id,
                    "assigned_to_name": user_names.get(history.assigned_to_id),
                    "note": history.note,
                }

        if activity.activity_type == "escalated":
            escalation = _closest_match(
                escalations,
                occurred_at,
                "created_at",
                consumed_escalations,
            )
            if escalation is not None:
                consumed_escalations.add(escalation.id)
                metadata["escalation"] = {
                    "escalation_id": escalation.id,
                    "reason": escalation.reason,
                    "escalated_from_id": escalation.escalated_from_id,
                    "escalated_from_name": user_names.get(escalation.escalated_from_id),
                    "escalated_to_id": escalation.escalated_to_id,
                    "escalated_to_name": user_names.get(escalation.escalated_to_id),
                }

        if activity.activity_type == "lead_deleted":
            audit = _closest_match(
                deletion_audits,
                occurred_at,
                "deleted_at",
                consumed_deletions,
            )
            if audit is not None:
                consumed_deletions.add(audit.id)
                metadata["deletion_audit"] = {
                    "audit_id": audit.id,
                    "previous_status": audit.previous_status,
                    "deleted_by_id": audit.deleted_by_id,
                    "deleted_by_name": audit.deleted_by_full_name,
                    "sale_amount": audit.sale_amount,
                    "invoice_number": audit.invoice_number,
                }

        if activity.activity_type == "lead_restored":
            audit = _closest_match(
                deletion_audits,
                occurred_at,
                "restored_at",
                consumed_restorations,
            )
            if audit is not None:
                consumed_restorations.add(audit.id)
                metadata["restoration"] = {
                    "audit_id": audit.id,
                    "restored_by_id": audit.restored_by_id,
                    "restored_by_name": user_names.get(audit.restored_by_id),
                }

        # اگر این فعالیت یک پیگیری بعدی تعیین کرده، در متادیتا دیده شود
        if activity.next_follow_up is not None:
            metadata["next_follow_up"] = activity.next_follow_up.isoformat()
        if activity.outcome:
            metadata["outcome"] = activity.outcome

        events.append(
            {
                "event_id": f"activity-{activity.id}",
                "source": "activity",
                "event_type": activity.activity_type,
                "title": activity.title,
                "description": activity.description,
                "actor_id": activity.user_id,
                "actor_name": user_names.get(activity.user_id),
                "occurred_at": occurred_at,
                "metadata": metadata,
            }
        )

    # ----------------------------------------------------------
    # ۲) ارجاع‌های بدون رویداد متناظر (داده‌های قدیمی)
    # ----------------------------------------------------------
    for history in assignments:
        if history.id in consumed_assignments:
            continue

        events.append(
            {
                "event_id": f"assignment-{history.id}",
                "source": "assignment",
                "event_type": "lead_assigned",
                "title": "ارجاع پرونده",
                "description": history.note,
                "actor_id": history.assigned_by_id,
                "actor_name": user_names.get(history.assigned_by_id),
                "occurred_at": _aware(history.assigned_at),
                "metadata": {
                    "assignment": {
                        "assignment_id": history.id,
                        "assigned_by_id": history.assigned_by_id,
                        "assigned_by_name": user_names.get(history.assigned_by_id),
                        "assigned_to_id": history.assigned_to_id,
                        "assigned_to_name": user_names.get(history.assigned_to_id),
                        "note": history.note,
                    }
                },
            }
        )

    # ----------------------------------------------------------
    # ۳) اسکالیشن‌های بدون رویداد متناظر
    # ----------------------------------------------------------
    for escalation in escalations:
        if escalation.id in consumed_escalations:
            continue

        events.append(
            {
                "event_id": f"escalation-{escalation.id}",
                "source": "escalation",
                "event_type": "escalated",
                "title": "ارجاع اضطراری به مدیر",
                "description": escalation.reason,
                "actor_id": escalation.escalated_from_id,
                "actor_name": user_names.get(escalation.escalated_from_id),
                "occurred_at": _aware(escalation.created_at),
                "metadata": {
                    "escalation": {
                        "escalation_id": escalation.id,
                        "reason": escalation.reason,
                        "escalated_from_id": escalation.escalated_from_id,
                        "escalated_from_name": user_names.get(escalation.escalated_from_id),
                        "escalated_to_id": escalation.escalated_to_id,
                        "escalated_to_name": user_names.get(escalation.escalated_to_id),
                    }
                },
            }
        )

    # ----------------------------------------------------------
    # ۴) حذف‌ها و احیاهای بدون رویداد متناظر (پرونده‌های حذف‌شده
    #    پیش از افزودن اکتیویتی‌های lead_deleted/lead_restored)
    # ----------------------------------------------------------
    for audit in deletion_audits:
        if audit.id not in consumed_deletions:
            events.append(
                {
                    "event_id": f"deletion-{audit.id}",
                    "source": "deletion_audit",
                    "event_type": "lead_deleted",
                    "title": "پرونده حذف شد",
                    "description": (
                        f"پرونده «{audit.customer_name}» با وضعیت قبلی "
                        f"{audit.previous_status} حذف شد."
                    ),
                    "actor_id": audit.deleted_by_id,
                    "actor_name": audit.deleted_by_full_name,
                    "occurred_at": _aware(audit.deleted_at),
                    "metadata": {
                        "deletion_audit": {
                            "audit_id": audit.id,
                            "previous_status": audit.previous_status,
                            "deleted_by_id": audit.deleted_by_id,
                            "deleted_by_name": audit.deleted_by_full_name,
                            "sale_amount": audit.sale_amount,
                            "invoice_number": audit.invoice_number,
                        }
                    },
                }
            )

        if audit.restored_at is not None and audit.id not in consumed_restorations:
            events.append(
                {
                    "event_id": f"restore-{audit.id}",
                    "source": "deletion_audit",
                    "event_type": "lead_restored",
                    "title": "پرونده احیا شد",
                    "description": "پرونده‌ی حذف‌شده توسط مدیر احیا شد.",
                    "actor_id": audit.restored_by_id,
                    "actor_name": user_names.get(audit.restored_by_id),
                    "occurred_at": _aware(audit.restored_at),
                    "metadata": {
                        "restoration": {
                            "audit_id": audit.id,
                            "restored_by_id": audit.restored_by_id,
                            "restored_by_name": user_names.get(audit.restored_by_id),
                        }
                    },
                }
            )

    # ----------------------------------------------------------
    # ۵) فایل‌های ضمیمه (در جدول فعالیت‌ها ثبت نمی‌شوند)
    # ----------------------------------------------------------
    for attachment in attachments:
        events.append(
            {
                "event_id": f"attachment-{attachment.id}",
                "source": "attachment",
                "event_type": "attachment_uploaded",
                "title": "بارگذاری فایل",
                "description": attachment.file_name,
                "actor_id": attachment.uploaded_by_id,
                "actor_name": user_names.get(attachment.uploaded_by_id),
                "occurred_at": _aware(attachment.created_at),
                "metadata": {
                    "attachment": {
                        "attachment_id": attachment.id,
                        "file_name": attachment.file_name,
                        "file_path": attachment.file_path,
                    }
                },
            }
        )

    # ----------------------------------------------------------
    # مرتب‌سازی نهایی: جدیدترین رویداد ابتدا
    # ----------------------------------------------------------
    events.sort(
        key=lambda event: event["occurred_at"] or datetime_min(),
        reverse=True,
    )
    return events


def datetime_min():
    """مقدار کمینه برای رویدادهایی که به‌ندرت زمان ندارند."""
    from datetime import datetime
    return datetime.min.replace(tzinfo=timezone.utc)
