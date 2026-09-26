from sqlalchemy.orm import Session

from app.models.activity import Activity
from app.models.lead import Lead
from app.models.user import User
from app.schemas.activity import ActivityCreate
from app.schemas.activity import ACTION_TYPES_REQUIRING_FOLLOWUP
from datetime import datetime, timezone

def create_activity(
    db: Session,
    lead: Lead, # فرض بر این است که مدل Lead در این فایل شناخته شده است
    current_user: User,
    activity_data: ActivityCreate,
    commit: bool = True,
):
    activity = Activity(
        lead_id=lead.id,
        user_id=current_user.id,
        activity_type=activity_data.activity_type,
        title=activity_data.title,
        description=activity_data.description,
        outcome=activity_data.outcome,
        next_follow_up=activity_data.next_follow_up,
        no_followup_reason=activity_data.no_followup_reason,
   )
    db.add(activity)

    # آپدیت زمان «آخرین تماس واقعی با مشتری» — قبلاً این مقدار برای هر نوع
    # رویداد (حتی رویدادهای سیستمی مثل lead_created/status_change) آپدیت
    # می‌شد؛ یعنی همان لحظه‌ی ساخت لید، last_contact_at پر می‌شد و «قانون ۱»
    # (یادآوری ۶۰ دقیقه‌ای عدم تماس) هرگز فعال نمی‌شد چون به نظر می‌رسید
    # همین الان تماسی گرفته شده. حالا فقط اقدام‌های واقعیِ انسانی (تماس،
    # جلسه، واتساپ، پیامک و...) به‌عنوان «تماس» حساب می‌شوند.
    if activity_data.activity_type in ACTION_TYPES_REQUIRING_FOLLOWUP:
        lead.last_contact_at = datetime.now(timezone.utc)

    # اگر هنگام ثبت این اقدام، پیگیری بعدی مشخص شده، مقدار «فعلی» روی خود لید هم به‌روز می‌شود
    # (فیلد next_follow_up روی Activity، تاریخچه را نگه می‌دارد؛ این مقدار روی Lead، «آخرین» را نشان می‌دهد)
    #
    # برای اقدام‌های انسانی (ACTION_TYPES_REQUIRING_FOLLOWUP)، اسکیمای
    # ActivityCreate تضمین می‌کند یا next_follow_up پر شده یا
    # no_followup_reason. پس اگر next_follow_up خالی است ولی این یک
    # اقدام انسانی است، یعنی کارشناس عمداً «بدون پیگیری» را انتخاب کرده
    # و باید مقدار قبلیِ next_follow_up روی لید پاک شود — قبلاً این حالت
    # نادیده گرفته می‌شد و لید با یک تاریخ پیگیریِ قدیمی و منقضی برای
    # همیشه در فیلتر «پیگیری‌های عقب‌افتاده» گیر می‌کرد. رویدادهای سیستمی
    # (تغییر وضعیت، ارجاع و...) هرگز نه next_follow_up دارند و نه
    # no_followup_reason، و نباید پیگیریِ فعلیِ لید را دست بزنند.
    if activity_data.next_follow_up is not None:
        lead.next_follow_up = activity_data.next_follow_up
        # سررسید تازه‌ای تنظیم شد؛ اگر سررسید قبلی قبلاً یادآوری کرده
        # بود، این پرچم باید بازنشانی شود تا «قانون ۴» بتواند دوباره
        # برای همین لید (با تاریخ جدید) یادآوری بسازد.
        lead.follow_up_notified = False
    elif activity_data.activity_type in ACTION_TYPES_REQUIRING_FOLLOWUP:
        lead.next_follow_up = None
        lead.follow_up_notified = False

    # ثبت هر اقدام واقعی (نه رویداد سیستمی) یعنی پرونده دیگر «رهاشده» نیست
    if activity_data.activity_type in ACTION_TYPES_REQUIRING_FOLLOWUP:
        lead.is_escalated = False

    if commit:
        db.commit()
        db.refresh(activity)
        db.refresh(lead)

    return activity


def get_lead_activities(
    db: Session,
    lead: Lead,
):
    return (
        db.query(Activity)
        .filter(Activity.lead_id == lead.id)
        .order_by(Activity.created_at.desc())
        .all()
    )
