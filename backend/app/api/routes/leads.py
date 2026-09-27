import mimetypes
import os
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.auth.dependencies import get_current_user
from app.crud.activity import create_activity, get_lead_activities
from app.crud.assignment_history import get_lead_assignment_history
from app.crud.attachment import (
    create_attachment,
    get_attachment_by_id,
    get_lead_attachments,
)
from app.crud.audit_log import create_audit_log
from app.crud.lead import (
    _assert_invoice_editable,
    InvoiceLockedError,
    assign_lead,
    count_leads,
    create_lead,
    delete_lead,
    get_my_lead_by_id,
    get_my_leads,
    get_pipeline_counts,
    get_related_leads,
    search_leads,
    update_lead,
    update_lead_followup,
    update_lead_status,
)
from app.crud.lead_escalation import get_lead_escalations
from app.crud.lead_submission import get_lead_submissions_with_submitter
from app.crud.product import get_product
from app.crud.sale_item import add_sale_item, get_lead_sale_items, set_sale_items
from app.crud.task import create_task, get_lead_task_by_id, get_lead_tasks, update_task_status
from app.crud.user import get_user
from app.database.database import get_db
from app.models.lead import Lead
from app.models.user import User
from app.permissions.permission import (
    LEAD_ASSIGNABLE_ROLES,
    can_assign_any_lead,
    can_view_all_leads,
)
from app.schemas.activity import ACTION_TYPES_REQUIRING_FOLLOWUP, ActivityCreate, ActivityResponse
from app.schemas.assignment_history import AssignmentHistoryResponse
from app.schemas.attachment import AttachmentResponse
from app.schemas.lead import (
    FINAL_FACTOR_STATUS,
    LeadAssign,
    LeadCreate,
    LeadCreateAttachedResponse,
    LeadFollowUpUpdate,
    LeadResponse,
    LeadStatusUpdate,
    LeadSubmissionResponse,
    LeadUpdate,
    PipelineCountsResponse,
)
from app.schemas.lead_deletion_audit import LeadDeleteResponse
from app.schemas.lead_escalation import LeadEscalationResponse
from app.schemas.sale_item import SaleItemCreate, SaleItemResponse
from app.schemas.task import TaskCreate, TaskResponse, TaskStatusUpdate
from app.crud.notification import create_notification

router = APIRouter(
    prefix="/leads",
    tags=["Leads"],
)


def _validate_sale_item_products(db: Session, items) -> None:
    for item in items:
        product = get_product(db, item.product_id)
        if not product or not product.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product {item.product_id} not found or inactive.",
            )


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_new_lead(
    lead_data: LeadCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LeadResponse | LeadCreateAttachedResponse:
    lead = create_lead(db, lead_data, current_user)
    create_audit_log(
        db,
        current_user.id,
        "create",
        "lead",
        lead.id,
        f"Lead '{lead.customer_name}' created or attached as duplicate.",
    )

    # SECURITY: when the mobile number matches an existing lead owned by
    # someone else, `create_lead` attaches this submission as a duplicate
    # and returns that OTHER user's Lead object. A caller who cannot view
    # that lead (not the owner, not a can_view_all_leads role) must never
    # receive its fields back — doing so leaks another customer's name,
    # need, source, and owner_id to an unrelated user. Return a minimal,
    # non-identifying acknowledgment instead; the real owner is already
    # notified separately inside register_duplicate_submission.
    is_owner = lead.owner_id == current_user.id
    if not is_owner and not can_view_all_leads(current_user):
        return LeadCreateAttachedResponse()

    return lead


@router.get("/my", response_model=list[LeadResponse])
def read_my_leads(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_my_leads(db, current_user)


@router.get("/pipeline", response_model=PipelineCountsResponse)
def read_pipeline_counts(
    search: str | None = Query(None, description="جستجوی اختیاری روی نتایج پایپ‌لاین"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    تعداد پرونده‌ها به تفکیک مرحله — با دامنه‌ی دسترسی نقش.
    جایگزین چندین درخواست موازی فرانت‌اند برای شمارش مراحل.
    """
    return get_pipeline_counts(db, current_user, search=search)


@router.get("/", response_model=list[LeadResponse])
def search_all_leads(
    response: Response,
    search: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    smart_filter: str | None = Query(
        None,
        description="today_followup | overdue | no_activity | critical | new | open | escalated",
    ),
    owner_id: int | None = Query(
        None,
        description="فیلتر مالکیت پرونده‌ها (بخش «تیم فروش» پنل ادمین). فقط برای نقش‌های مدیریتی اعمال می‌شود.",
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    with_total: bool = Query(
        False,
        description="در صورت فعال بودن، تعداد کل نتایج در هدر X-Total-Count برمی‌گردد",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    leads = search_leads(
        db=db,
        current_user=current_user,
        search=search,
        status=status_filter,
        smart_filter=smart_filter,
        skip=skip,
        limit=limit,
        owner_id=owner_id,
    )
    if with_total:
        total = count_leads(
            db,
            current_user,
            search=search,
            status=status_filter,
            smart_filter=smart_filter,
            owner_id=owner_id,
        )
        response.headers["X-Total-Count"] = str(total)
    return leads


@router.get("/{lead_id}", response_model=LeadResponse)
def read_lead(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lead = get_my_lead_by_id(db, lead_id, current_user)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return lead


@router.get("/{lead_id}/timeline", response_model=list[ActivityResponse])
def lead_timeline(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lead = get_my_lead_by_id(db, lead_id, current_user)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return get_lead_activities(db, lead)


@router.get("/{lead_id}/duplicate-history", response_model=list[LeadSubmissionResponse])
def read_lead_duplicate_history(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lead = get_my_lead_by_id(db, lead_id, current_user)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return get_lead_submissions_with_submitter(db, lead)


@router.get("/{lead_id}/related-leads", response_model=list[LeadResponse])
def read_related_leads(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lead = get_my_lead_by_id(db, lead_id, current_user)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return get_related_leads(db, lead, current_user)


@router.patch("/{lead_id}", response_model=LeadResponse)
def update_lead_details(
    lead_id: int,
    lead_data: LeadUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    ویرایش اطلاعات هویتی پرونده (نام، موبایل، منبع، نیاز).
    کلیدهای نرمال‌شده به‌صورت خودکار بازمحاسبه می‌شوند؛ موبایل
    تکراری با پرونده‌ی دیگر پذیرفته نمی‌شود.
    """
    lead = get_my_lead_by_id(db, lead_id, current_user)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    try:
        updated_lead = update_lead(db, lead, lead_data, current_user)
    except InvoiceLockedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    create_audit_log(
        db,
        current_user.id,
        "update",
        "lead",
        lead_id,
        f"Lead '{updated_lead.customer_name}' details updated.",
    )
    return updated_lead


@router.patch("/{lead_id}/status", response_model=LeadResponse)
def change_lead_status(
    lead_id: int,
    status_data: LeadStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lead = get_my_lead_by_id(db, lead_id, current_user)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    if status_data.sale_items:
        _validate_sale_item_products(db, status_data.sale_items)
    atomic_sale = status_data.status == FINAL_FACTOR_STATUS and bool(status_data.sale_items)
    try:
        updated_lead = update_lead_status(
            db,
            lead,
            status_data,
            current_user,
            commit=not atomic_sale,
        )
    except InvoiceLockedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if atomic_sale:
        set_sale_items(
            db,
            updated_lead,
            status_data.sale_items,
            current_user,
            sync_sale_amount=(status_data.sale_amount is None),
            commit=False,
        )
        db.commit()
        db.refresh(updated_lead)
    create_audit_log(
        db,
        current_user.id,
        "status_change",
        "lead",
        lead_id,
        f"Status changed to {status_data.status}",
    )
    return updated_lead


@router.get("/{lead_id}/sale-items", response_model=list[SaleItemResponse])
def read_lead_sale_items(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lead = get_my_lead_by_id(db, lead_id, current_user)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return get_lead_sale_items(db, lead)


@router.post(
    "/{lead_id}/sale-items",
    response_model=SaleItemResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_lead_sale_item(
    lead_id: int,
    item_data: SaleItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lead = get_my_lead_by_id(db, lead_id, current_user)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")

    # Reload under a row lock so invoice status cannot become stale mid-write.
    lead = (
        db.query(Lead)
        .populate_existing()
        .filter(Lead.id == lead_id, Lead.is_deleted == False)
        .with_for_update()
        .first()
    )
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    if not can_view_all_leads(current_user) and lead.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")

    # قفل فاکتور: افزودن قلم فروش به پرونده‌ی فاکتورشده هم باید مسدود باشد،
    # وگرنه کارشناس می‌توانست از مسیر تغییر وضعیت عبور کند و مبلغ را عوض کند.
    try:
        _assert_invoice_editable(lead, current_user)
    except InvoiceLockedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    product = get_product(db, item_data.product_id)
    if not product or not product.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Product {item_data.product_id} not found or inactive.",
        )
    return add_sale_item(db, lead, current_user, item_data)


@router.post("/{lead_id}/activities", response_model=ActivityResponse, status_code=status.HTTP_201_CREATED)
def create_lead_activity(
    lead_id: int,
    activity_data: ActivityCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lead = get_my_lead_by_id(db, lead_id, current_user)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    # SECURITY/AUDIT: system event types (status_change, lead_deleted,
    # escalated, lead_restored, duplicate_detected, ...) are written only
    # by the server as side effects of real operations. Accepting them
    # here let any user forge audit-trail events (e.g. a fake "deleted"
    # or "escalated" entry) in a lead's timeline.
    if activity_data.activity_type not in ACTION_TYPES_REQUIRING_FOLLOWUP:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "این نوع فعالیت فقط توسط سیستم ثبت می‌شود. انواع مجاز: "
                f"{', '.join(sorted(ACTION_TYPES_REQUIRING_FOLLOWUP))}"
            ),
        )
    return create_activity(db, lead, current_user, activity_data)


@router.get("/{lead_id}/activities", response_model=list[ActivityResponse])
def read_lead_activities(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lead = get_my_lead_by_id(db, lead_id, current_user)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return get_lead_activities(db, lead)


@router.post("/{lead_id}/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_lead_task(
    lead_id: int,
    task_data: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lead = get_my_lead_by_id(db, lead_id, current_user)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    if task_data.assigned_to_id is not None and task_data.assigned_to_id != current_user.id:
        # پیش از این هیچ بررسی‌ای نبود: شناسه‌ی ناموجود به خطای کلید خارجی
        # (۴۰۹ با پیام گمراه‌کننده) می‌خورد، و ارجاع به کاربری که پرونده را
        # نمی‌بیند وظیفه‌ای «یتیم» می‌ساخت که در «وظایف من» هیچ‌کس ظاهر نمی‌شد.
        assignee = get_user(db, task_data.assigned_to_id)
        if not assignee or not assignee.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="کاربر مقصد وظیفه وجود ندارد یا غیرفعال است.",
            )
        if assignee.id != lead.owner_id and not can_view_all_leads(assignee):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="وظیفه فقط به مالک پرونده یا نقش‌های نظارتی قابل ارجاع است.",
            )
    task = create_task(db, lead, current_user, task_data)
    create_audit_log(
        db,
        current_user.id,
        "create",
        "task",
        task.id,
        f"Task '{task.title}' created for Lead {lead_id}",
    )
    return task


@router.get("/{lead_id}/tasks", response_model=list[TaskResponse])
def read_lead_tasks(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lead = get_my_lead_by_id(db, lead_id, current_user)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return get_lead_tasks(db, lead)


@router.patch("/{lead_id}/tasks/{task_id}/status", response_model=TaskResponse)
def change_lead_task_status(
    lead_id: int,
    task_id: int,
    status_data: TaskStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lead = get_my_lead_by_id(db, lead_id, current_user)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    task = get_lead_task_by_id(db, lead, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    return update_task_status(db, lead, task, current_user, status_data)


@router.patch("/{lead_id}/assign", response_model=LeadResponse)
def assign_lead_to_user(
    lead_id: int,
    assign_data: LeadAssign,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lead = get_my_lead_by_id(db, lead_id, current_user)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found.")
    is_manager = can_assign_any_lead(current_user)
    is_owner = lead.owner_id == current_user.id
    if not (is_manager or is_owner):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")
    owner = get_user(db, assign_data.owner_id)
    if not owner:
        raise HTTPException(status_code=404, detail="User not found.")
    # ارجاع به کاربر غیرفعال (اخراج/تعلیق‌شده) پذیرفته نمی‌شود، وگرنه
    # پرونده در کارتابلی می‌افتد که هیچ‌کس به آن سر نمی‌زند.
    if not owner.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ارجاع به کاربر غیرفعال ممکن نیست.",
        )
    if owner.role not in LEAD_ASSIGNABLE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ارجاع پرونده فقط به اعضای تیم فروش/مدیریت فروش مجاز است.",
        )
    assigned_lead = assign_lead(db, lead, owner, current_user, note=assign_data.note)
    create_audit_log(
        db,
        current_user.id,
        "assign",
        "lead",
        lead_id,
        f"Assigned to user ID: {assign_data.owner_id}",
    )
    if owner.id != current_user.id:
        # اعلان درون‌برنامه‌ای هنگام ارجاع پرونده.
        # پیش از این تنها کانال اطلاع‌رسانی، پیام ربات بله بود؛ چون
        # این استقرار هیچ اتصالی به ربات ندارد، معادل درون‌برنامه‌ای آن
        # جایگزین شد تا کارشناس همچنان از ارجاع پرونده باخبر شود.
        create_notification(
            db,
            user_id=owner.id,
            notification_type="lead_assigned",
            title="پرونده‌ی جدید به شما ارجاع داده شد",
            message=f"پرونده‌ی «{lead.customer_name}» ({lead.mobile}) به شما ارجاع داده شد.",
            lead_id=lead.id,
        )
    return assigned_lead


@router.get("/{lead_id}/assignments", response_model=list[AssignmentHistoryResponse])
def read_lead_assignment_history(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lead = get_my_lead_by_id(db, lead_id, current_user)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found.")
    return get_lead_assignment_history(db, lead)


@router.get("/{lead_id}/escalations", response_model=list[LeadEscalationResponse])
def read_lead_escalations(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lead = get_my_lead_by_id(db, lead_id, current_user)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found.")
    return get_lead_escalations(db, lead)


@router.delete("/{lead_id}", response_model=LeadDeleteResponse)
def soft_delete_lead(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lead = get_my_lead_by_id(db, lead_id, current_user)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found.")
    delete_lead(db, lead, current_user)
    create_audit_log(
        db,
        current_user.id,
        "delete",
        "lead",
        lead_id,
        f"Lead '{lead.customer_name}' deleted.",
    )
    return {"status": "deleted"}


@router.patch("/{lead_id}/followup", response_model=LeadResponse)
def set_lead_followup(
    lead_id: int,
    followup_data: LeadFollowUpUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lead = get_my_lead_by_id(db, lead_id, current_user)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found.")
    updated_lead = update_lead_followup(db, lead, followup_data, current_user)
    create_audit_log(
        db,
        current_user.id,
        "followup_set",
        "lead",
        lead_id,
        f"Follow-up set to {followup_data.next_follow_up}",
    )
    return updated_lead


# مسیر ذخیره‌سازی فایل‌ها روی سرور
UPLOAD_DIR = "uploads/leads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# پسوندهای مجاز برای پیوست پرونده؛ هر چیز دیگری رد می‌شود.
ALLOWED_ATTACHMENT_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt",
    ".png", ".jpg", ".jpeg", ".webp", ".gif",
    ".zip", ".rar", ".7z",
    ".mp3", ".ogg", ".wav", ".m4a",
    ".mp4", ".mov",
}

# حداکثر حجم مجاز هر پیوست (۲۰ مگابایت)
MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024

# اندازه‌ی هر تکه هنگام نوشتن روی دیسک
_UPLOAD_CHUNK_SIZE = 1024 * 1024


def _safe_attachment_name(raw_name: str | None) -> tuple[str, str]:
    """
    نام امن برای ذخیره‌سازی فایل.

    نام خام کلاینت هرگز مستقیم در مسیر استفاده نمی‌شود: پیش از این
    یک نام مثل «../../app/main.py» می‌توانست از پوشه‌ی uploads خارج
    شود. اینجا فقط basename نگه داشته می‌شود، پسوند در برابر فهرست
    سفید بررسی می‌شود و نام نهایی با UUID ساخته می‌شود.

    خروجی: (نام نمایشی امن، نام یکتای روی دیسک)
    """
    original = os.path.basename(raw_name or "").strip() or "file"
    # حذف جداکننده‌های مسیر و بایت تهی که ممکن است از کلاینت بیاید
    original = original.replace("\\", "_").replace("/", "_").replace("\x00", "")
    extension = os.path.splitext(original)[1].lower()
    if extension not in ALLOWED_ATTACHMENT_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "این نوع فایل مجاز نیست. پسوندهای مجاز: "
                f"{', '.join(sorted(ALLOWED_ATTACHMENT_EXTENSIONS))}"
            ),
        )
    # DB column file_name is String(255): truncate display name instead of
    # letting an over-long client filename crash the INSERT with a 500.
    if len(original) > 255:
        stem, ext = os.path.splitext(original)
        original = stem[: 255 - len(ext)] + ext
    stored_name = f"{uuid4().hex}{extension}"
    return original, stored_name


@router.post("/{lead_id}/attachments", response_model=AttachmentResponse, status_code=status.HTTP_201_CREATED)
def upload_lead_attachment(
    lead_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lead = get_my_lead_by_id(db, lead_id, current_user)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found.")

    display_name, stored_name = _safe_attachment_name(file.filename)
    file_path = os.path.join(UPLOAD_DIR, f"{lead_id}_{stored_name}")

    # دفاع عمقی: مسیر نهایی باید حتماً داخل UPLOAD_DIR باقی بماند
    upload_root = os.path.realpath(UPLOAD_DIR)
    if os.path.commonpath([os.path.realpath(file_path), upload_root]) != upload_root:
        raise HTTPException(status_code=400, detail="Invalid file path.")

    # نوشتن تکه‌تکه همراه با کنترل حجم؛ فایل بیش از حد مجاز حذف می‌شود
    written = 0
    try:
        with open(file_path, "wb") as buffer:
            while True:
                chunk = file.file.read(_UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_ATTACHMENT_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="حجم فایل بیش از حد مجاز (۲۰ مگابایت) است.",
                    )
                buffer.write(chunk)
    except HTTPException:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise
    except Exception:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise

    # فایل همین الان روی دیسک نوشته شد؛ اگر ثبت رکورد DB شکست بخورد،
    # فایل باید پاک شود وگرنه سند مشتری به‌صورت «یتیم» و غیرقابل‌دسترس
    # روی دیسک باقی می‌ماند (نه DB آن را می‌شناسد، نه هیچ مسیری به آن
    # ختم می‌شود).
    try:
        attachment = create_attachment(db, lead, current_user, display_name, file_path)
    except Exception:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise
    create_audit_log(
        db,
        current_user.id,
        "upload_attachment",
        "lead",
        lead_id,
        f"File '{file.filename}' uploaded.",
    )
    return attachment


@router.get("/{lead_id}/attachments", response_model=list[AttachmentResponse])
def read_lead_attachments(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lead = get_my_lead_by_id(db, lead_id, current_user)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found.")
    return get_lead_attachments(db, lead_id)


@router.get("/{lead_id}/attachments/{attachment_id}/download")
def download_lead_attachment(
    lead_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    دانلود پیوست با بررسی مجوز.

    پیش از این فایل‌ها از طریق mount استاتیک «/uploads» بدون هیچ احراز
    هویتی سرو می‌شدند؛ هر کسی که آدرس فایل را داشت (مثلاً از لاگ یا
    لینک اشتراک‌شده) می‌توانست سند مشتری را بدون ورود دانلود کند.
    حالا تنها مسیر دریافت فایل، همین اندپوینت است و فقط کاربرانی که
    خودِ پرونده را می‌بینند به پیوست آن دسترسی دارند.
    """
    lead = get_my_lead_by_id(db, lead_id, current_user)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found.")
    attachment = get_attachment_by_id(db, attachment_id, lead_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found.")

    # مسیر فقط از رکورد دیتابیس (سمت سرور نوشته شده) خوانده می‌شود؛
    # با این حال مهار containment برای دفاع عمقی باقی می‌ماند.
    real_path = os.path.realpath(attachment.file_path)
    upload_root = os.path.realpath(UPLOAD_DIR)
    if os.path.commonpath([real_path, upload_root]) != upload_root:
        raise HTTPException(status_code=400, detail="Invalid file path.")
    if not os.path.isfile(real_path):
        raise HTTPException(status_code=404, detail="File is missing on server.")

    media_type = (
        mimetypes.guess_type(attachment.file_name)[0] or "application/octet-stream"
    )
    return FileResponse(real_path, media_type=media_type, filename=attachment.file_name)