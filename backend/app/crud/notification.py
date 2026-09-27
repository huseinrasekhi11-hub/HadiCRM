from datetime import datetime
from datetime import timezone

from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.models.task import Task
from app.models.lead import Lead
from app.models.user import User
from app.models.notification import Notification


def get_notifications(
    db: Session,
    current_user: User,
):
    now = datetime.now(timezone.utc)

    # وظایف بازِ سررسیدگذشته — فقط روی پرونده‌های حذف‌نشده. وظیفه‌ی
    # «canceled» هم دیگر «باز» نیست (پیش از این فقط done مستثنی بود و
    # شمارشِ خلاصه را باد می‌کرد).
    overdue_tasks = (
        db.query(Task)
        .join(Lead, Task.lead_id == Lead.id)
        .filter(Task.assigned_to_id == current_user.id)
        .filter(Task.status.notin_(["done", "canceled"]))
        .filter(Task.is_deleted == False)
        .filter(Lead.is_deleted == False)
        .filter(Task.due_at < now)
        .count()
    )

    # پرونده‌های من — حذف نرم‌شده‌ها نباید در شمارش خلاصه بمانند؛
    # پیش از این شامل آن‌ها می‌شد و عددِ کارتِ داشبورد با فهرست واقعی
    # پرونده‌ها نمی‌خواند.
    my_leads = (
        db.query(Lead)
        .filter(Lead.owner_id == current_user.id)
        .filter(Lead.is_deleted == False)
        .count()
    )

    return {
        "overdue_tasks": overdue_tasks,
        "my_leads": my_leads,
    }


# === توابع جدید: نوتیفیکیشن‌های واقعی داشبورد ===
# (فرق دارد با get_notifications بالا که فقط یک خلاصه‌ی شمارشی است)

def create_notification(
    db: Session,
    user_id: int,
    notification_type: str,
    title: str,
    message: str,
    lead_id: int | None = None,
    commit: bool = True,
):
    notification = Notification(
        user_id=user_id,
        lead_id=lead_id,
        notification_type=notification_type,
        title=title,
        message=message,
    )
    db.add(notification)

    if commit:
        db.commit()
        db.refresh(notification)

    return notification


def get_notification_feed(
    db: Session,
    current_user: User,
    unread_only: bool = False,
    limit: int = 50,
):
    """
    فید نوتیفیکیشن به همراه نام و موبایل مشتریِ لید مرتبط (در صورت وجود)،
    تا رابط کاربری بتواند دکمه‌ی «تماس» را مستقیم از داخل نوتیفیکیشن نشان دهد
    بدون نیاز به یک درخواست جداگانه به ازای هر نوتیفیکیشن.
    """
    query = (
        db.query(Notification, Lead.customer_name, Lead.mobile)
        .outerjoin(Lead, Notification.lead_id == Lead.id)
        .filter(Notification.user_id == current_user.id)
    )

    # A soft-deleted lead is intentionally outside the normal user's
    # visibility boundary. Old notifications can outlive the lead, so
    # suppress those notifications for ordinary users instead of leaking
    # customer identity/message text after deletion. Admin/CEO users retain
    # the historical notification view and can use the dedicated deletion
    # audit/timeline surfaces.
    from app.constants.roles import Roles
    if current_user.role not in (Roles.ADMIN, Roles.CEO):
        query = query.filter(
            or_(Notification.lead_id.is_(None), Lead.is_deleted == False)
        )

    if unread_only:
        query = query.filter(Notification.is_read == False)

    rows = query.order_by(Notification.created_at.desc()).limit(limit).all()

    return [
        {
            "id": n.id,
            "lead_id": n.lead_id,
            "notification_type": n.notification_type,
            "title": n.title,
            "message": n.message,
            "is_read": n.is_read,
            "created_at": n.created_at,
            "lead_customer_name": customer_name,
            "lead_mobile": mobile,
        }
        for n, customer_name, mobile in rows
    ]


def get_unread_count(db: Session, current_user: User) -> int:
    return (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id)
        .filter(Notification.is_read == False)
        .count()
    )


def mark_notification_read(db: Session, notification_id: int, current_user: User):
    notification = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
        .first()
    )

    if not notification:
        return None

    notification.is_read = True
    db.commit()
    db.refresh(notification)
    return notification


def mark_all_notifications_read(db: Session, current_user: User):
    (
        db.query(Notification)
        .filter(
            Notification.user_id == current_user.id,
            Notification.is_read == False,
        )
        .update({"is_read": True})
    )
    db.commit()