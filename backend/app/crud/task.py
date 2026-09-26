from datetime import datetime
from datetime import timezone

from sqlalchemy.orm import Session

from app.crud.activity import create_activity
from app.models.lead import Lead
from app.models.task import Task
from app.models.user import User
from app.permissions.permission import can_view_all_leads
from app.schemas.activity import ActivityCreate
from app.schemas.task import TaskCreate
from app.schemas.task import TaskStatusUpdate


def create_task(
    db: Session,
    lead: Lead,
    current_user: User,
    task_data: TaskCreate,
):
    assigned_to_id = task_data.assigned_to_id or current_user.id
    task = Task(
        lead_id=lead.id,
        created_by_id=current_user.id,
        assigned_to_id=assigned_to_id,
        title=task_data.title,
        description=task_data.description,
        due_at=task_data.due_at,
        status="pending",
    )

    db.add(task)
    db.flush()

    create_activity(
        db,
        lead,
        current_user,
        ActivityCreate(
            activity_type="task_created",
            title="Task created",
            description=f"{task.title} is due at {task.due_at.isoformat()}.",
        ),
        commit=False,
    )

    db.commit()
    db.refresh(task)

    return task


def get_lead_tasks(
    db: Session,
    lead: Lead,
):
    return (
        db.query(Task)
        .filter(Task.lead_id == lead.id)
        .order_by(Task.due_at.asc())
        .all()
    )


def get_lead_task_by_id(
    db: Session,
    lead: Lead,
    task_id: int,
):
    return (
        db.query(Task)
        .filter(Task.lead_id == lead.id)
        .filter(Task.id == task_id)
        .first()
    )


def get_my_tasks(
    db: Session,
    current_user: User,
):
    """
    وظایف در انتظارِ محول‌شده به کاربر جاری.

    اصلاح: پیش از این فقط بر اساس assigned_to_id فیلتر می‌شد، بدون بررسی
    اینکه کاربر هنوز به لید مربوطه دسترسی دارد یا نه. وقتی پرونده‌ای به
    کارشناس دیگری ارجاع/بازتخصیص می‌شد، وظیفه‌ی قبلی (که همچنان
    assigned_to_id قدیمی را دارد) در «وظایف من» باقی می‌ماند؛ کلیک روی آن
    تلاش می‌کرد GET /leads/{id} را برای پرونده‌ای بزند که کاربر دیگر مالکش
    نیست، و آن اندپوینت (get_my_lead_by_id) با ۴۰۴ پاسخ می‌داد — همان خطای
    «دریافت اطلاعات پرونده» که در رابط کاربری دیده می‌شد.

    این پرس‌وجو اکنون به همان قاعده‌ی دیدِ get_my_lead_by_id پایبند است:
    برای نقش‌های بدون دید کامل، فقط وظایفِ پرونده‌هایی که هنوز متعلق به
    خودِ کاربر هستند برگردانده می‌شود.
    """
    query = (
        db.query(Task)
        .join(Lead, Lead.id == Task.lead_id)
        .filter(Task.assigned_to_id == current_user.id)
        .filter(Task.status == "pending")
        .filter(Lead.is_deleted == False)
    )
    if not can_view_all_leads(current_user):
        query = query.filter(Lead.owner_id == current_user.id)
    return query.order_by(Task.due_at.asc()).all()


def update_task_status(
    db: Session,
    lead: Lead,
    task: Task,
    current_user: User,
    status_data: TaskStatusUpdate,
):
    task.status = status_data.status
    task.completed_at = (
        datetime.now(timezone.utc)
        if status_data.status == "done"
        else None
    )

    if status_data.status == "done":
        create_activity(
            db,
            lead,
            current_user,
            ActivityCreate(
                activity_type="task_completed",
                title="Task completed",
                description=task.title,
            ),
            commit=False,
        )

    db.commit()
    db.refresh(task)

    return task
