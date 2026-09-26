"""
سیستم یادآوری خودکار HadiFlow

این فایل دقیقاً سه قانون کسب‌وکار را پیاده می‌کند (سند فرآیند فروش):

قانون ۱ — یادآوری ۶۰ دقیقه‌ای:
    اگر پرونده‌ای ارجاع داده شد ولی تا ۶۰ دقیقه بعد هیچ اقدامی
    (تماس/فعالیت) روی آن ثبت نشد، به کارشناس یادآوری می‌شود.

قانون ۲ — یادآوری روزانه‌ی ساعت ۸ صبح:
    هر روز صبح، خلاصه‌ی تمام «پرونده‌های باز» هر کارشناس برای او
    ارسال می‌شود. (این تابع از قبل وجود داشت؛ فقط باگ فیلتر وضعیت
    آن که لیستی هاردکد بود، به «هر چیزی جز برد/باخت» اصلاح شد.)

قانون ۳ — ارجاع اضطراری پس از ۳ روز رکود:
    اگر ۳ روز از آخرین فعالیت روی یک پرونده‌ی باز بگذرد، پرونده
    به‌صورت خودکار از کارشناس گرفته و به مدیر (نقش CEO) ارجاع
    داده می‌شود.

توابع و نام‌های قبلی (send_daily_morning_reminders، start_scheduler)
عمداً حفظ شده‌اند تا نقاطی از پروژه که به آن‌ها وابسته‌اند نشکنند.
"""
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from app.database.database import SessionLocal
from app.models.lead import Lead
from app.models.user import User
from app.constants.roles import Roles
from app.core import jalali
from app.crud.notification import create_notification
from app.crud.assignment_history import log_assignment
from app.crud.lead_escalation import create_escalation
from app.crud.activity import create_activity
from app.schemas.activity import ActivityCreate
from app.schemas.lead import CLOSED_STATUSES


NO_CONTACT_WINDOW_MINUTES = 60
ESCALATION_THRESHOLD_DAYS = 3


def _aware(dt):
    """
    تضمین tz-aware بودن.

    بخشی از ستون‌های قدیمی (مثل status_updated_at) ساعت محلی تهران را
    به‌صورت naive ذخیره می‌کنند. مقایسه‌ی مستقیم آن‌ها با یک datetime
    آگاه، TypeError می‌دهد و کل job را ساکت از کار می‌اندازد.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _get_designated_manager(db):
    """
    مدیر مقصدِ ارجاع اضطراری (قانون ۳).

    اولویت: مدیرعامل فعال → ادمین فعال. پیش از این فقط اولین CEO
    انتخاب می‌شد و اگر هیچ CEO‌ای وجود نداشت، تشدید بی‌صدا هیچ کاری
    نمی‌کرد (پرونده‌های راکد برای همیشه رها می‌شدند).
    """
    manager = (
        db.query(User)
        .filter(User.role == Roles.CEO, User.is_active == True)
        .order_by(User.id)
        .first()
    )
    if manager:
        return manager
    return (
        db.query(User)
        .filter(User.role == Roles.ADMIN, User.is_active == True)
        .order_by(User.id)
        .first()
    )


def send_daily_morning_reminders():
    """
    قانون ۲: هر روز ساعت ۸ صبح، خلاصه‌ی پرونده‌های باز هر کارشناس ارسال می‌شود.

    باگ قبلی: فیلتر status.in_([...]) با یک لیست هاردکد بود که با اضافه
    شدن وضعیت‌های جدید هماهنگ نمی‌ماند. اصلاح شد به «هر وضعیتی جز برد/باخت»
    که دقیقاً همان تعریف «پرونده‌ی باز» در سند کسب‌وکار است.
    """
    print("⏳ [Scheduler] Rule 2: Daily morning digest triggered.")
    db = SessionLocal()
    try:
        open_leads = db.query(Lead).filter(
            Lead.status.notin_(CLOSED_STATUSES),
            Lead.is_deleted == False,
        ).all()

        user_leads = {}
        for lead in open_leads:
            user_leads.setdefault(lead.owner_id, []).append(lead)

        for owner_id, leads in user_leads.items():
            owner = db.query(User).filter(User.id == owner_id).first()
            # کاربر غیرفعال نباید گزارش صبحگاهی بگیرد
            if not owner or not owner.is_active:
                continue

            # commit=False: به‌جای یک commit به ازای هر کاربر، همه‌ی
            # اعلان‌ها یک‌جا در پایان ثبت می‌شوند (کاهش فشار و جلوگیری
            # از حالت نیمه‌کاره در صورت خطا وسط حلقه).
            create_notification(
                db,
                user_id=owner.id,
                notification_type="daily_followup_digest",
                title="پرونده‌های باز امروز",
                message=f"شما {len(leads)} پرونده‌ی باز دارید که باید امروز پیگیری کنید.",
                commit=False,
            )

        # یک commit واحد برای تمام اعلان‌های این اجرا
        db.commit()
    finally:
        db.close()


def check_no_contact_reminders():
    """
    قانون ۱: اگر ۶۰ دقیقه از آخرین ارجاع یک پرونده گذشته و هیچ تماس/فعالیتی
    روی آن ثبت نشده باشد، به کارشناسِ مسئول یادآوری می‌شود (یک‌بار، تا
    ارجاع بعدی این پرچم دوباره صفر شود).
    """
    print("⏳ [Scheduler] Rule 1: No-contact 60-minute check triggered.")
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=NO_CONTACT_WINDOW_MINUTES)

        candidates = db.query(Lead).filter(
            Lead.is_deleted == False,
            Lead.status.notin_(CLOSED_STATUSES),
            Lead.sla_notified == False,
            Lead.last_assigned_at.isnot(None),
            Lead.last_assigned_at <= cutoff,
        ).all()

        for lead in candidates:
            # اگر از زمان ارجاع تماسی ثبت نشده (last_contact_at خالی است یا قدیمی‌تر از ارجاع)
            has_contact_since_assignment = (
                lead.last_contact_at is not None
                and _aware(lead.last_contact_at) >= _aware(lead.last_assigned_at)
            )
            if has_contact_since_assignment:
                # کارشناس به‌موقع تماس گرفته — دیگر نیازی به یادآوری نیست.
                # این پرچم را هم اینجا True می‌کنیم، وگرنه این پرونده
                # (چون last_assigned_at <= cutoff هنوز صادق است) در هر
                # اجرای بعدی این job دوباره candidate می‌شود و برای
                # همیشه بی‌جهت بررسی می‌شود، حتی با اینکه هرگز یادآوری
                # دومی ارسال نخواهد شد (به‌خاطر همین continue).
                lead.sla_notified = True
                db.commit()
                continue

            owner = db.query(User).filter(User.id == lead.owner_id).first()
            if not owner:
                continue

            create_notification(
                db,
                user_id=owner.id,
                notification_type="no_contact_reminder",
                title="یادآوری: پیگیری نشده",
                message=f"۶۰ دقیقه از ارجاع پرونده‌ی «{lead.customer_name}» گذشته و هنوز اقدامی ثبت نشده.",
                lead_id=lead.id,
                commit=True,
            )

            lead.sla_notified = True
            db.commit()
            print(f"✅ [Scheduler] Rule 1: reminder sent for lead {lead.id}.")
    finally:
        db.close()


def escalate_stale_leads():
    """
    قانون ۳: اگر ۳ روز از آخرین فعالیت روی یک پرونده‌ی باز بگذرد، پرونده
    به‌صورت خودکار به مدیر (CEO) ارجاع داده می‌شود و این اتفاق در
    تایم‌لاین، تاریخچه‌ی ارجاع، و جدول escalations ثبت می‌شود.
    """
    print("⏳ [Scheduler] Rule 3: 3-day escalation check triggered.")
    db = SessionLocal()
    try:
        manager = _get_designated_manager(db)
        if not manager:
            print(
                "❌ [Scheduler] Rule 3: no active ceo/admin found; cannot escalate."
            )
            return

        cutoff = datetime.now(timezone.utc) - timedelta(days=ESCALATION_THRESHOLD_DAYS)

        candidates = db.query(Lead).filter(
            Lead.is_deleted == False,
            Lead.status.notin_(CLOSED_STATUSES),
            Lead.is_escalated == False,
            # پرونده‌هایی که از قبل دست خود مدیر هستند در همان کوئری
            # کنار گذاشته می‌شوند، نه داخل حلقه.
            Lead.owner_id != manager.id,
        ).all()

        for lead in candidates:
            # «آخرین فعالیت» باید جدیدترینِ سه سیگنال باشد: آخرین تماس،
            # زمان ساخت، و آخرین ارجاع. قبلاً last_assigned_at اینجا در
            # نظر گرفته نمی‌شد؛ یعنی یک پرونده‌ی قدیمیِ بدون تماس که
            # همین چند دقیقه پیش به کارشناس جدیدی ارجاع شده بود، در
            # همان اجرای بعدیِ این job (چون created_at هنوز قدیمی بود)
            # بلافاصله از دست کارشناس گرفته و به مدیر ارجاع می‌شد — بدون
            # اینکه کارشناس حتی فرصت رسیدگی داشته باشد.
            last_activity = max(
                _aware(lead.last_contact_at or lead.created_at),
                _aware(lead.last_assigned_at) or _aware(lead.created_at),
            )

            if last_activity > cutoff:
                continue  # هنوز به ۳ روز رکود نرسیده

            if lead.owner_id == manager.id:
                continue  # از قبل دست مدیر است؛ نیازی به ارجاع مجدد نیست

            old_owner = db.query(User).filter(User.id == lead.owner_id).first()
            old_owner_id = lead.owner_id

            # ارجاع خودکار
            lead.owner_id = manager.id
            lead.last_assigned_at = datetime.now(timezone.utc)
            lead.sla_notified = False
            lead.is_escalated = True

            create_activity(
                db,
                lead,
                manager,  # عامل رویداد: خود سیستم به نمایندگی از مدیر ثبت می‌شود
                ActivityCreate(
                    activity_type="escalated",
                    title="ارجاع خودکار به مدیر",
                    description="۳ روز از آخرین فعالیت گذشت و پرونده به مدیر ارجاع داده شد.",
                ),
                commit=False,
            )

            log_assignment(
                db,
                lead,
                assigned_by=old_owner or manager,
                assigned_to=manager,
                note="ارجاع خودکار به دلیل عدم فعالیت به مدت ۳ روز",
                commit=False,
            )

            create_escalation(
                db,
                lead,
                escalated_from_id=old_owner_id,
                escalated_to_id=manager.id,
                reason="no_activity_3_days",
                commit=False,
            )

            db.commit()
            db.refresh(lead)

            create_notification(
                db,
                user_id=manager.id,
                notification_type="lead_escalated_manager",
                title="پرونده‌ای به شما ارجاع اضطراری شد",
                message=f"پرونده‌ی «{lead.customer_name}» به دلیل عدم فعالیت به شما ارجاع داده شد.",
                lead_id=lead.id,
                commit=True,
            )

            if old_owner:
                create_notification(
                    db,
                    user_id=old_owner.id,
                    notification_type="lead_escalated",
                    title="پرونده از شما گرفته شد",
                    message=f"پرونده‌ی «{lead.customer_name}» به دلیل عدم فعالیت به مدیر ارجاع داده شد.",
                    lead_id=lead.id,
                    commit=True,
                )

            print(f"✅ [Scheduler] Rule 3: lead {lead.id} escalated to manager {manager.id}.")
    finally:
        db.close()


def start_scheduler():
    scheduler = BackgroundScheduler()

    # قانون ۲: هر روز ساعت ۸:۰۰ صبح به وقت تهران.
    # قبلاً timezone مشخص نشده بود؛ APScheduler برای cron جاب‌ها به‌صورت
    # پیش‌فرض از timezone محلیِ سرور استفاده می‌کند، نه وقت تهران. روی
    # سروری که به وقت UTC اجرا می‌شود، «۸ صبح» واقعاً ساعت ۱۱:۳۰ به وقت
    # تهران فعال می‌شد، نه ۸ صبح طبق قاعده‌ی کسب‌وکار.
    scheduler.add_job(
        send_daily_morning_reminders, 'cron', hour=8, minute=0, timezone=jalali.TEHRAN_TZ
    )

    # قانون ۱: هر ۵ دقیقه بررسی می‌شود که آیا پرونده‌ای بیش از ۶۰ دقیقه بدون اقدام مانده
    scheduler.add_job(check_no_contact_reminders, 'interval', minutes=5)

    # قانون ۳: هر ساعت بررسی می‌شود که آیا پرونده‌ای ۳ روز بدون فعالیت مانده
    scheduler.add_job(escalate_stale_leads, 'interval', hours=1)

    scheduler.start()
    return scheduler
