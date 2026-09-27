import hashlib
from datetime import datetime, timedelta, timezone
from sqlalchemy import case, func, or_, text
from sqlalchemy.orm import Session
from app.core.jalali import jalali_today_bounds_utc, naive_tehran_now
from app.core.text_normalization import normalize_mobile, normalize_persian_text
from app.crud.activity import create_activity
from app.crud.assignment_history import log_assignment
from app.crud.lead_deletion_audit import record_lead_deletion
from app.crud.notification import create_notification
from app.models.lead import Lead
from app.models.lead_deletion_audit import LeadDeletionAudit
from app.models.task import Task
from app.models.lead_submission import (
    MATCHED_BY_MOBILE,
    MATCHED_BY_MOBILE_AND_NAME,
    LeadSubmission,
)
from app.models.user import User
from app.permissions.permission import can_view_all_leads
from app.schemas.activity import ActivityCreate
from app.schemas.lead import CLOSED_STATUSES
from app.schemas.lead import FINAL_FACTOR_STATUS
from app.schemas.lead import LeadCreate
from app.schemas.lead import LeadFollowUpUpdate
from app.schemas.lead import LeadStatusUpdate
from app.schemas.lead import LeadUpdate
from app.schemas.lead import PIPELINE_ORDER
from app.schemas.lead import canonical_status

class InvoiceLockedError(PermissionError):
    """
    تلاش برای تغییر فاکتور نهاییِ قفل‌شده توسط کاربری که مجوز ندارد.
    لایه‌ی روت این خطا را به HTTP 403 تبدیل می‌کند.
    """


def _assert_invoice_editable(lead: Lead, current_user: User) -> None:
    """
    قفل فاکتور: پس از آنکه پرونده به وضعیت «فاکتور نهایی» رسید،
    کارشناس فروش دیگر اجازه‌ی ویرایش مبلغ/شماره فاکتور یا خارج‌کردن
    پرونده از این وضعیت را ندارد. فقط نقش‌های نظارتی (که دید کامل
    دارند) می‌توانند اصلاح کنند — آن هم با ثبت در تاریخچه.
    """
    if lead.status != FINAL_FACTOR_STATUS:
        return
    if can_view_all_leads(current_user):
        return
    raise InvoiceLockedError(
        "فاکتور نهایی ثبت شده است و توسط کارشناس قابل ویرایش نیست. "
        "برای اصلاح با مدیر تماس بگیرید."
    )


# ==========================================================
# کشف و اتصال لیدهای تکراری
# ==========================================================
def find_duplicate_lead(
    db: Session,
    mobile_normalized: str | None,
    customer_name_normalized: str | None,
) -> Lead | None:
    if not mobile_normalized:
        return None
    candidates = (
        db.query(Lead)
        .filter(
            Lead.is_deleted == False,
            Lead.mobile_normalized == mobile_normalized,
        )
        .order_by(Lead.created_at.asc(), Lead.id.asc())
        .all()
    )
    if not candidates:
        return None
    if customer_name_normalized:
        for candidate in candidates:
            if candidate.customer_name_normalized == customer_name_normalized:
                return candidate
    return candidates[0]


def register_duplicate_submission(
    db: Session,
    lead: Lead,
    lead_data: LeadCreate,
    current_user: User,
    mobile_normalized: str | None,
    customer_name_normalized: str | None,
) -> Lead:
    # Atomic increment: a read-modify-write here loses updates when two
    # duplicate submissions for the same lead arrive concurrently.
    db.query(Lead).filter(Lead.id == lead.id).update(
        {Lead.duplicate_count: func.coalesce(Lead.duplicate_count, 0) + 1},
        synchronize_session="fetch",
    )
    submission_index = lead.duplicate_count
    matched_by = MATCHED_BY_MOBILE
    if (
        customer_name_normalized
        and lead.customer_name_normalized == customer_name_normalized
    ):
        matched_by = MATCHED_BY_MOBILE_AND_NAME
    submission = LeadSubmission(
        lead_id=lead.id,
        submitted_by_id=current_user.id,
        customer_name=lead_data.customer_name,
        customer_name_normalized=customer_name_normalized,
        mobile=lead_data.mobile,
        mobile_normalized=mobile_normalized,
        need=lead_data.need,
        source=lead_data.source,
        notes=lead_data.notes,
        submission_index=submission_index,
        matched_by=matched_by,
    )
    db.add(submission)
    lead.duplicate_count = submission_index
    create_activity(
        db,
        lead,
        current_user,
        ActivityCreate(
            activity_type="duplicate_detected",
            title="ثبت تکراری لید",
            description=(
                f"ثبت تکراری برای «{lead_data.customer_name}» با شماره "
                f"{mobile_normalized or lead_data.mobile} به این پرونده متصل شد."
            ),
        ),
        commit=False,
    )
    db.commit()
    db.refresh(lead)
    db.refresh(submission)
    if lead.owner_id and lead.owner_id != current_user.id:
        create_notification(
            db,
            user_id=lead.owner_id,
            notification_type="duplicate_submission",
            title="ثبت تکراری برای پرونده‌ی شما",
            message=(
                f"ثبت جدیدی برای پرونده‌ی «{lead.customer_name}» توسط "
                f"{current_user.full_name} ثبت و به پرونده‌ی شما متصل شد."
            ),
            lead_id=lead.id,
        )
    return lead


def _lock_mobile_for_create(db: Session, mobile_normalized: str | None) -> None:
    """
    قفل مشورتی (advisory) در سطح تراکنش روی شماره‌ی نرمال‌شده.

    بدون این قفل، دو درخواست هم‌زمانِ «ثبت لید» با یک شماره هر دو
    find_duplicate_lead را خالی می‌دیدند و دو پرونده‌ی مستقل می‌ساختند
    (در آزمایش با ۸ درخواست هم‌زمان، ۳ پرونده‌ی جداگانه ساخته شد) —
    یعنی قرارداد «یک پرونده‌ی فعال به ازای هر شماره» نقض می‌شد و
    ثبت‌های بعدی به پرونده‌ی اشتباه می‌چسبیدند.

    قفل تا پایان تراکنش (commit/rollback) نگه داشته می‌شود؛ بنابراین
    درخواست‌های هم‌زمان با همان شماره پشت سر هم اجرا می‌شوند و دومی
    پرونده‌ی اولی را می‌بیند و به آن متصل می‌شود. فقط PostgreSQL از
    این قابلیت پشتیبانی می‌کند؛ روی سایر دیتابیس‌ها بی‌اثر است.
    """
    if not mobile_normalized:
        return
    if db.get_bind().dialect.name != "postgresql":
        return
    digest = hashlib.sha256(mobile_normalized.encode("utf-8")).digest()
    key = int.from_bytes(digest[:8], "big", signed=True)
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def create_lead(
    db: Session,
    lead_data: LeadCreate,
    current_user: User,
):
    mobile_normalized = normalize_mobile(lead_data.mobile)
    customer_name_normalized = normalize_persian_text(lead_data.customer_name)
    _lock_mobile_for_create(db, mobile_normalized)
    existing_lead = find_duplicate_lead(
        db,
        mobile_normalized=mobile_normalized,
        customer_name_normalized=customer_name_normalized,
    )
    if existing_lead is not None:
        return register_duplicate_submission(
            db,
            existing_lead,
            lead_data,
            current_user,
            mobile_normalized=mobile_normalized,
            customer_name_normalized=customer_name_normalized,
        )
    lead = Lead(
        customer_name=lead_data.customer_name,
        mobile=lead_data.mobile,
        mobile_normalized=mobile_normalized,
        customer_name_normalized=customer_name_normalized,
        duplicate_count=0,
        source=lead_data.source,
        need=lead_data.need,
        status="new",
        created_by_id=current_user.id,
        owner_id=current_user.id,
        last_assigned_at=datetime.now(timezone.utc),
    )
    db.add(lead)
    db.flush()
    create_activity(
        db,
        lead,
        current_user,
        ActivityCreate(
            activity_type="lead_created",
            title="Lead created",
            description=f"Lead created from {lead.source}.",
        ),
        commit=False,
    )
    log_assignment(
        db,
        lead,
        assigned_by=current_user,
        assigned_to=current_user,
        note="ایجاد پرونده",
        commit=False,
    )
    db.commit()
    db.refresh(lead)
    return lead


# ==========================================================
# فیلتر مشترک — یک نقطه‌ی تعریف برای جستجو/لیست/شمارش/پایپ‌لاین
# ==========================================================
def _apply_lead_filters(
    query,
    current_user: User,
    search: str | None = None,
    status: str | None = None,
    smart_filter: str | None = None,
    owner_id: int | None = None,
):
    # دامنه‌ی مالکیت فقط از سیاست متمرکز اعمال می‌شود
    if not can_view_all_leads(current_user):
        query = query.filter(Lead.owner_id == current_user.id)
    elif owner_id is not None:
        # مدیر می‌تواند دامنه را به پرونده‌های یک عضو تیم محدود کند
        # (بخش «تیم فروش» پنل ادمین). برای کاربران عادی بی‌اثر است،
        # چون دامنه‌شان همین حالا روی خودشان قفل شده است.
        query = query.filter(Lead.owner_id == owner_id)
    if search:
        # 1) کاراکترهای ویژه‌ی LIKE خنثی می‌شوند تا «%» یا «_» تایپ‌شده
        #    توسط کاربر به‌عنوان wildcard عمل نکند.
        # 2) ورودی نرمال می‌شود تا ارقام فارسی/عربی («۰۹۱۲…») هم با
        #    ستون mobile_normalized مطابقت پیدا کند.
        raw = search.strip()
        escaped = raw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        name_term = normalize_persian_text(raw) or raw
        name_escaped = (
            name_term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        mobile_term = normalize_mobile(raw)

        conditions = [
            Lead.customer_name.ilike(f"%{escaped}%", escape="\\"),
            Lead.customer_name_normalized.ilike(f"%{name_escaped}%", escape="\\"),
            Lead.mobile.ilike(f"%{escaped}%", escape="\\"),
        ]
        if mobile_term:
            mobile_escaped = (
                mobile_term.replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            conditions.append(
                Lead.mobile_normalized.ilike(f"%{mobile_escaped}%", escape="\\")
            )
        else:
            conditions.append(
                Lead.mobile_normalized.ilike(f"%{escaped}%", escape="\\")
            )

        query = query.filter(or_(*conditions))
    if status:
        query = query.filter(Lead.status == canonical_status(status))
    if smart_filter:
        now = datetime.now(timezone.utc)
        # «امروز» بر اساس روز جلالیِ منطقه‌زمانی تهران تعریف می‌شود
        today_start, today_end = jalali_today_bounds_utc()
        open_filter = Lead.status.notin_(CLOSED_STATUSES)
        if smart_filter == "today_followup":
            query = query.filter(
                open_filter,
                Lead.next_follow_up.isnot(None),
                Lead.next_follow_up >= today_start,
                Lead.next_follow_up < today_end,
            )
        elif smart_filter == "overdue":
            query = query.filter(
                open_filter,
                Lead.next_follow_up.isnot(None),
                Lead.next_follow_up < now,
            )
        elif smart_filter == "no_activity":
            query = query.filter(open_filter, Lead.next_follow_up.is_(None))
        elif smart_filter == "critical":
            cutoff = now - timedelta(days=14)
            query = query.filter(
                open_filter,
                func.coalesce(Lead.last_contact_at, Lead.created_at) < cutoff,
            )
        elif smart_filter == "new":
            query = query.filter(Lead.status == "new")
        elif smart_filter == "open":
            query = query.filter(open_filter)
        elif smart_filter == "escalated":
            query = query.filter(Lead.is_escalated == True)
    return query


def get_my_leads(db: Session, current_user: User):
    query = db.query(Lead).filter(Lead.is_deleted == False)
    if not can_view_all_leads(current_user):
        query = query.filter(Lead.owner_id == current_user.id)
    return query.order_by(Lead.created_at.desc()).all()


def get_my_lead_by_id(db: Session, lead_id: int, current_user: User):
    query = db.query(Lead).filter(
        Lead.id == lead_id,
        Lead.is_deleted == False,
    )
    if not can_view_all_leads(current_user):
        query = query.filter(Lead.owner_id == current_user.id)
    return query.first()


def get_related_leads(db: Session, lead: Lead, current_user: User):
    if not lead.mobile_normalized:
        return []
    query = db.query(Lead).filter(
        Lead.is_deleted == False,
        Lead.id != lead.id,
        Lead.mobile_normalized == lead.mobile_normalized,
    )
    if not can_view_all_leads(current_user):
        query = query.filter(Lead.owner_id == current_user.id)
    return query.order_by(Lead.created_at.desc()).all()


def get_team_member_stats(db: Session, user_id: int) -> dict:
    """
    آمار خلاصه‌ی یک عضو تیم برای بخش «تیم فروش» پنل ادمین:
    شمار پرونده‌ها به تفکیک وضعیت (فقط پرونده‌های فعالِ مالکیت)،
    جمع فروش قطعی، تعداد وظایف باز و تعداد حذف‌های ثبت‌شده.
    """
    rows = (
        db.query(Lead.status, func.count(Lead.id))
        .filter(
            Lead.owner_id == user_id,
            Lead.is_deleted == False,  # noqa: E712
        )
        .group_by(Lead.status)
        .all()
    )
    by_status = {status_value: int(count) for status_value, count in rows}

    totals = (
        db.query(
            func.count(Lead.id),
            func.coalesce(
                func.sum(
                    case(
                        (Lead.status == FINAL_FACTOR_STATUS, Lead.sale_amount),
                        else_=0,
                    )
                ),
                0,
            ),
        )
        .filter(
            Lead.owner_id == user_id,
            Lead.is_deleted == False,  # noqa: E712
        )
        .one()
    )

    open_tasks = (
        db.query(func.count(Task.id))
        .join(Lead, Task.lead_id == Lead.id)
        .filter(
            Lead.owner_id == user_id,
            Lead.is_deleted == False,  # noqa: E712
            Task.status.notin_(["done", "canceled"]),
        )
        .scalar()
        or 0
    )

    deleted_count = (
        db.query(func.count(LeadDeletionAudit.id))
        .filter(LeadDeletionAudit.owner_id == user_id)
        .scalar()
        or 0
    )

    return {
        "total": int(totals[0] or 0),
        "open": sum(c for s, c in by_status.items() if s not in CLOSED_STATUSES),
        "won": by_status.get(FINAL_FACTOR_STATUS, 0),
        "lost": by_status.get("closed_lost", 0),
        "by_status": by_status,
        "total_sales": int(totals[1] or 0),
        "open_tasks": int(open_tasks),
        "deleted_count": int(deleted_count),
    }


def search_leads(
    db: Session,
    current_user: User,
    search: str | None = None,
    status: str | None = None,
    smart_filter: str | None = None,
    skip: int = 0,
    limit: int = 20,
    owner_id: int | None = None,
):
    query = db.query(Lead).filter(Lead.is_deleted == False)
    query = _apply_lead_filters(query, current_user, search, status, smart_filter, owner_id=owner_id)
    return (
        query.order_by(Lead.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def count_leads(
    db: Session,
    current_user: User,
    search: str | None = None,
    status: str | None = None,
    smart_filter: str | None = None,
    owner_id: int | None = None,
) -> int:
    """تعداد کل نتایج با همان فیلترهای جستجو — برای صفحه‌بندی فرانت‌اند."""
    query = db.query(func.count(Lead.id)).filter(Lead.is_deleted == False)
    query = _apply_lead_filters(query, current_user, search, status, smart_filter, owner_id=owner_id)
    return int(query.scalar() or 0)


def get_pipeline_counts(
    db: Session,
    current_user: User,
    search: str | None = None,
) -> dict:
    """
    خلاصه‌ی پایپ‌لاین با دامنه‌ی دسترسی نقش:
    همه‌ی مراحل رسمی (صفرگذاری‌شده) + تعداد کل.
    """
    query = db.query(Lead.status, func.count(Lead.id)).filter(Lead.is_deleted == False)
    query = _apply_lead_filters(query, current_user, search=search)
    rows = query.group_by(Lead.status).all()
    counts = {status_value: count for status_value, count in rows}
    stages = [
        {"status": status_value, "count": int(counts.get(status_value, 0))}
        for status_value in PIPELINE_ORDER
    ]
    return {
        "total": sum(stage["count"] for stage in stages),
        "stages": stages,
    }


# ==========================================================
# ویرایش اطلاعات پرونده
# ==========================================================
def update_lead(
    db: Session,
    lead: Lead,
    lead_data: LeadUpdate,
    current_user: User,
) -> Lead:
    """
    ویرایش هویت/نیاز/منبع پرونده با نگه‌داری کلیدهای نرمال.
    تغییر موبایل به شماره‌ای که متعلق به پرونده‌ی دیگری است
    پذیرفته نمی‌شود تا پرونده‌ها ناخواسته در هم ادغام نشوند.

    اگر فاکتور نهایی صادر شده باشد، پرونده برای کارشناس قفل است.
    """
    _assert_invoice_editable(lead, current_user)

    if lead_data.customer_name is not None:
        name = lead_data.customer_name.strip()
        lead.customer_name = name
        lead.customer_name_normalized = normalize_persian_text(name)
    if lead_data.mobile is not None:
        mobile_normalized = normalize_mobile(lead_data.mobile)
        if not mobile_normalized:
            raise ValueError("شماره موبایل واردشده معتبر نیست.")

        # Reuse the same per-mobile PostgreSQL advisory lock as lead creation.
        # Without it, two existing leads can concurrently change their phone
        # to the same normalized value after both pass the clash query.
        _lock_mobile_for_create(db, mobile_normalized)

        clash = (
            db.query(Lead)
            .filter(
                Lead.is_deleted == False,
                Lead.id != lead.id,
                Lead.mobile_normalized == mobile_normalized,
            )
            .first()
        )
        if clash is not None:
            raise ValueError(
                "این شماره موبایل متعلق به پرونده‌ی دیگری است و قابل جایگزینی نیست."
            )
        lead.mobile = lead_data.mobile.strip()
        lead.mobile_normalized = mobile_normalized
    if lead_data.source is not None:
        lead.source = lead_data.source.strip()
    if lead_data.need is not None:
        lead.need = lead_data.need.strip() or None
    db.commit()
    db.refresh(lead)
    return lead


# ==========================================================
# تغییر وضعیت با وضعیت رسمی (final_factor)
# ==========================================================
def update_lead_status(
    db: Session,
    lead: Lead,
    status_data: LeadStatusUpdate,
    current_user: User,
):
    # قفل فاکتور پیش از هر تغییری بررسی می‌شود
    _assert_invoice_editable(lead, current_user)

    old_status = lead.status
    lead.status = status_data.status
    # مهم: این ستون باید همیشه naive و به وقت محلی تهران باشد (طبق
    # قرارداد مستندشده در app/core/jalali.py و پیش‌فرض مدل، get_tehran_time).
    # قبلاً اینجا datetime.now(timezone.utc) نوشته می‌شد — چون این ستون
    # بدون timezone=True است، درایور دیتابیس صرفاً عدد ساعت دیواری را
    # ذخیره می‌کند (بدون تبدیل)، پس همان لحظه‌ی واقعی بسته به این‌که از
    # کدام مسیر نوشته شده، دو عدد متفاوت (با ~۳٫۵ ساعت اختلاف) در همین
    # ستون ذخیره می‌شد و گزارش‌های فروشِ روزانه/تقویم جلالی را به‌هم
    # می‌ریخت.
    lead.status_updated_at = naive_tehran_now()
    if status_data.status == "closed_lost":
        lead.loss_reason = status_data.loss_reason
        if status_data.resolution_notes:
            lead.resolution_notes = status_data.resolution_notes
    if status_data.status == FINAL_FACTOR_STATUS:
        # شماره فاکتور «یک‌بارنویس» است: اگر قبلاً صادر شده، دوباره
        # بازنویسی نمی‌شود مگر اینکه کاربر نقش نظارتی داشته باشد.
        if status_data.sale_amount is not None:
            lead.sale_amount = status_data.sale_amount
        if status_data.sold_products:
            lead.sold_products = status_data.sold_products
        if status_data.invoice_number:
            if lead.invoice_number and not can_view_all_leads(current_user):
                raise InvoiceLockedError(
                    "شماره فاکتور قبلاً ثبت شده است و قابل تغییر نیست."
                )
            lead.invoice_number = status_data.invoice_number
        if status_data.resolution_notes:
            lead.resolution_notes = status_data.resolution_notes
    create_activity(
        db,
        lead,
        current_user,
        ActivityCreate(
            activity_type="status_change",
            title="Lead status changed",
            description=f"Status changed from {old_status} to {lead.status}.",
        ),
        commit=False,
    )
    db.commit()
    db.refresh(lead)
    return lead


def assign_lead(
    db: Session,
    lead: Lead,
    owner: User,
    current_user: User,
    note: str | None = None,
):
    old_owner = lead.owner_id
    lead.owner_id = owner.id
    lead.last_assigned_at = datetime.now(timezone.utc)
    lead.sla_notified = False
    lead.is_escalated = False
    create_activity(
        db,
        lead,
        current_user,
        ActivityCreate(
            activity_type="lead_assigned",
            title="Lead Assigned",
            description=f"Lead assigned from user {old_owner} to user {owner.id}",
        ),
        commit=False,
    )
    log_assignment(
        db,
        lead,
        assigned_by=current_user,
        assigned_to=owner,
        note=note,
        commit=False,
    )
    db.commit()
    db.refresh(lead)
    if owner.id != current_user.id:
        create_notification(
            db,
            user_id=owner.id,
            notification_type="lead_assigned",
            title="پرونده‌ی جدید به شما ارجاع شد",
            message=f"پرونده‌ی «{lead.customer_name}» به شما ارجاع داده شد.",
            lead_id=lead.id,
        )
    return lead


def get_pipeline(db: Session):
    rows = (
        db.query(Lead.status, func.count(Lead.id))
        .filter(Lead.is_deleted == False)
        .group_by(Lead.status)
        .all()
    )
    return [{"status": status_value, "count": count} for status_value, count in rows]


# ==========================================================
# حذف نرم + ممیزی نامحسوس
# ==========================================================
def delete_lead(db: Session, lead: Lead, deleted_by: User):
    record_lead_deletion(db, lead, deleted_by, commit=False)
    create_activity(
        db,
        lead,
        deleted_by,
        ActivityCreate(
            activity_type="lead_deleted",
            title="پرونده حذف شد",
            description=f"پرونده «{lead.customer_name}» توسط {deleted_by.full_name} حذف شد.",
        ),
        commit=False,
    )
    lead.is_deleted = True
    lead.deleted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(lead)
    return lead


def update_lead_followup(
    db: Session,
    lead: Lead,
    followup_data: LeadFollowUpUpdate,
    current_user: User,
):
    lead.next_follow_up = followup_data.next_follow_up
    # سررسید (جدید یا پاک‌شده) دستی تغییر کرد؛ پرچمِ «قانون ۴» باید
    # بازنشانی شود تا این سررسید بتواند دوباره یادآوری بسازد. این
    # مسیر جدا از create_activity است چون ActivityCreate اینجا
    # next_follow_up را پاس نمی‌دهد (پیام آن را در description تعبیه
    # می‌کند)، پس منطق بازنشانیِ داخل create_activity این حالت را پوشش
    # نمی‌دهد.
    lead.follow_up_notified = False
    create_activity(
        db,
        lead,
        current_user,
        ActivityCreate(
            activity_type="followup_set",
            title="تنظیم زمان پیگیری",
            description=f"زمان پیگیری بعدی تنظیم شد برای: {lead.next_follow_up}",
        ),
        commit=False,
    )
    db.commit()
    db.refresh(lead)
    return lead