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

قانون ۴ (جدید) — یادآوری سررسید پیگیری:
    وقتی next_follow_up یک لید فرامی‌رسد، به کارشناسِ مسئول یک
    نوتیفیکیشنِ داخل‌سایت («این پیگیری الان سررسید شده») ارسال می‌شود.
    پیش از این هیچ رویدادی برای این لحظه وجود نداشت؛ next_follow_up
    فقط منفعلانه در فیلترها/داشبورد نمایش داده می‌شد و کارشناس فقط در
    صورتی متوجه سررسید می‌شد که خودش به سراغ صفحه‌ی «کارهای روزانه»
    برود. مثل قانون ۱ (sla_notified)، این یادآوری هم یک‌بار در ازای هر
    سررسید ارسال می‌شود (پرچم follow_up_notified) و با تنظیم دستیِ
    سررسید جدید توسط کارشناس دوباره فعال می‌شود.

توابع و نام‌های قبلی (send_daily_morning_reminders، start_scheduler)
عمداً حفظ شده‌اند تا نقاطی از پروژه که به آن‌ها وابسته‌اند نشکنند.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import functools

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import text

from app.database.database import SessionLocal, engine
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
from app.core.logger import app_logger


NO_CONTACT_WINDOW_MINUTES = 60
ESCALATION_THRESHOLD_DAYS = 3

# ==========================================================
# قفل تک‌نسخه‌ای jobها (multi-worker safety)
#
# APScheduler داخل lifespan هر فرایند API استارت می‌شود؛ با
# uvicorn --workers N یا چند کانتینر، هر job N بار اجرا و
# نوتیفیکیشن/ارجاع تکراری ساخته می‌شد. هر job پیش از اجرا یک
# advisory lock غیرمسدودکننده روی PostgreSQL می‌گیرد؛ اگر نمونه‌ی
# دیگری همان لحظه مشغول همان job باشد، این اجرا بدون اثر جانبی
# رد می‌شود. روی دیتابیس‌های غیر PostgreSQL (فقط تست‌های واحد)
# قفل بی‌اثر است و job مستقیم اجرا می‌شود.
# ==========================================================
_JOB_LOCK_KEYS = {
    "rule1_no_contact": 910001,
    "rule2_morning_digest": 910002,
    "rule3_escalation": 910003,
    "rule4_followup_due": 910004,
    "refresh_session_cleanup": 910005,
    "login_rate_event_cleanup": 910006,
}


@contextmanager
def _single_instance_lock(lock_name: str):
    """
    قفل advisory در سطح session روی یک اتصال اختصاصی.

    اتصال تا پایان بلوک job باز می‌ماند تا lock و unlock حتماً روی
    همان connection اجرا شوند (اتصالِ Session کاری بین commitها به
    pool برمی‌گردد و برای این کار قابل اتکا نیست).
    """
    key = _JOB_LOCK_KEYS[lock_name]
    if engine.dialect.name != "postgresql":
        yield True
        return
    conn = engine.connect()
    try:
        acquired = conn.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": key}
        ).scalar()
        if not acquired:
            yield False
            return
        try:
            yield True
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
    finally:
        conn.close()


def single_instance(lock_name: str):
    """دکوریتور: job فقط در یک فرایند/نسخه در هر لحظه اجرا می‌شود."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with _single_instance_lock(lock_name) as acquired:
                if not acquired:
                    app_logger.info(
                        f"[Scheduler] {lock_name}: another worker is already "
                        "running this job; skipping this tick."
                    )
                    return None
                return func(*args, **kwargs)

        return wrapper

    return decorator


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


@single_instance("rule2_morning_digest")
def send_daily_morning_reminders():
    """
    قانون ۲: هر روز ساعت ۸ صبح، خلاصه‌ی پرونده‌های باز هر کارشناس ارسال می‌شود.

    باگ قبلی: فیلتر status.in_([...]) با یک لیست هاردکد بود که با اضافه
    شدن وضعیت‌های جدید هماهنگ نمی‌ماند. اصلاح شد به «هر وضعیتی جز برد/باخت»
    که دقیقاً همان تعریف «پرونده‌ی باز» در سند کسب‌وکار است.
    """
    app_logger.info("[Scheduler] Rule 2: Daily morning digest triggered.")
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


def _process_no_contact_candidate(db, lead) -> None:
    """پردازش یک پرونده در قانون ۱ (در تراکنش مستقل)."""
    # اگر از زمان ارجاع تماسی ثبت نشده (last_contact_at خالی است یا قدیمی‌تر از ارجاع)
    has_contact_since_assignment = (
        lead.last_contact_at is not None
        and _aware(lead.last_contact_at) >= _aware(lead.last_assigned_at)
    )
    if has_contact_since_assignment:
        # کارشناس به‌موقع تماس گرفته — دیگر نیازی به یادآوری نیست.
        # این پرچم را هم اینجا True می‌کنیم، وگرنه این پرونده
        # (چون last_assigned_at <= cutoff هنوز صادق است) در هر
        # اجرای بعدی این job دوباره candidate می‌شود.
        lead.sla_notified = True
        db.commit()
        return

    owner = db.query(User).filter(User.id == lead.owner_id).first()
    if not owner:
        return

    create_notification(
        db,
        user_id=owner.id,
        notification_type="no_contact_reminder",
        title="یادآوری: پیگیری نشده",
        message=f"۶۰ دقیقه از ارجاع پرونده‌ی «{lead.customer_name}» گذشته و هنوز اقدامی ثبت نشده.",
        lead_id=lead.id,
        commit=False,
    )
    lead.sla_notified = True
    db.commit()
    app_logger.info(f"[Scheduler] Rule 1: reminder sent for lead {lead.id}.")


@single_instance("rule1_no_contact")
def check_no_contact_reminders():
    """
    قانون ۱: اگر ۶۰ دقیقه از آخرین ارجاع یک پرونده گذشته و هیچ تماس/فعالیتی
    روی آن ثبت نشده باشد، به کارشناسِ مسئول یادآوری می‌شود (یک‌بار، تا
    ارجاع بعدی این پرچم دوباره صفر شود).
    """
    app_logger.info("[Scheduler] Rule 1: No-contact 60-minute check triggered.")
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
            # خطای یک پرونده نباید پردازش بقیه را متوقف کند؛ پیش از این یک
            # استثنا کل job را ساکت از کار می‌انداخت و هیچ لاگی نمی‌ماند.
            try:
                _process_no_contact_candidate(db, lead)
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                app_logger.exception(f"[Scheduler] Rule 1 failed for lead {lead.id}: {exc}")
    finally:
        db.close()


def _process_due_followup(db, lead) -> None:
    """پردازش یک پرونده در قانون ۴ (در تراکنش مستقل)."""
    owner = db.query(User).filter(User.id == lead.owner_id).first()
    # کاربر غیرفعال نباید یادآوری بگیرد؛ ولی پرچم را هم اینجا True
    # می‌کنیم وگرنه این لید برای همیشه در هر اجرا candidate می‌ماند
    # بدون اینکه هرگز نوتیفیکیشنی واقعاً ارسال شود.
    if not owner or not owner.is_active:
        lead.follow_up_notified = True
        db.commit()
        return

    create_notification(
        db,
        user_id=owner.id,
        notification_type="follow_up_due",
        title="سررسید پیگیری",
        message=f"زمان پیگیریِ پرونده‌ی «{lead.customer_name}» فرا رسیده است.",
        lead_id=lead.id,
        commit=False,
    )
    lead.follow_up_notified = True
    db.commit()
    app_logger.info(f"[Scheduler] Rule 4: follow-up reminder sent for lead {lead.id}.")


@single_instance("rule4_followup_due")
def check_due_followups():
    """
    قانون ۴: وقتی زمانِ next_follow_up یک لید فرا می‌رسد (یعنی همین الان
    یا در گذشته است) و هنوز برای همین سررسید یادآوری نشده، به کارشناسِ
    مسئولِ آن لید یک نوتیفیکیشنِ داخل‌سایت ارسال می‌شود.

    این کار جدا از «قانون ۱» است: قانون ۱ فقط درباره‌ی عدم تماس در ۶۰
    دقیقه‌ی اول *بعد از ارجاع* است، نه سررسید پیگیریِ برنامه‌ریزی‌شده‌ای
    که خودِ کارشناس (هنگام ثبت یک تماس/یادداشت) تعیین کرده. پیش از این
    next_follow_up فقط منفعلانه در فیلترهای «امروز/عقب‌افتاده» و
    داشبورد نمایش داده می‌شد؛ اگر کارشناس در همان لحظه اپ را باز نکرده
    بود، هیچ‌چیز به او یادآوری نمی‌کرد.

    follow_up_notified یک پرچم یک‌بارمصرف است (مثل sla_notified در
    قانون ۱): بعد از ارسال یادآوری True می‌شود تا در اجراهای بعدیِ این
    job (هر ۵ دقیقه) دوباره برای همان سررسید نوتیفیکیشن تکراری نسازد.
    وقتی کارشناس سررسید جدیدی تنظیم می‌کند (یا آن را پاک می‌کند)، این
    پرچم در لایه‌ی CRUD (create_activity / update_lead_followup) به
    False بازمی‌گردد تا سررسید جدید بتواند دوباره یادآوری کند.
    """
    app_logger.info("[Scheduler] Rule 4: follow-up due check triggered.")
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)

        candidates = db.query(Lead).filter(
            Lead.is_deleted == False,
            Lead.status.notin_(CLOSED_STATUSES),
            Lead.follow_up_notified == False,
            Lead.next_follow_up.isnot(None),
            Lead.next_follow_up <= now,
        ).all()

        for lead in candidates:
            # خطای یک پرونده نباید پردازش بقیه را متوقف کند (همان
            # الگوی قانون ۱ و ۳).
            try:
                _process_due_followup(db, lead)
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                app_logger.exception(f"[Scheduler] Rule 4 failed for lead {lead.id}: {exc}")
    finally:
        db.close()


def _escalate_one_lead(db, lead, manager, cutoff) -> None:
    """ارجاع اضطراری یک پرونده به مدیر (در تراکنش مستقل)."""
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
        return  # هنوز به ۳ روز رکود نرسیده

    if lead.owner_id == manager.id:
        return  # از قبل دست مدیر است؛ نیازی به ارجاع مجدد نیست

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
        commit=False,
    )

    if old_owner:
        create_notification(
            db,
            user_id=old_owner.id,
            notification_type="lead_escalated",
            title="پرونده از شما گرفته شد",
            message=f"پرونده‌ی «{lead.customer_name}» به دلیل عدم فعالیت به مدیر ارجاع داده شد.",
            lead_id=lead.id,
            commit=False,
        )

    app_logger.info(f"[Scheduler] Rule 3: lead {lead.id} escalated to manager {manager.id}.")
    db.commit()


@single_instance("rule3_escalation")
def escalate_stale_leads():
    """
    قانون ۳: اگر ۳ روز از آخرین فعالیت روی یک پرونده‌ی باز بگذرد، پرونده
    به‌صورت خودکار به مدیر (CEO) ارجاع داده می‌شود و این اتفاق در
    تایم‌لاین، تاریخچه‌ی ارجاع، و جدول escalations ثبت می‌شود.
    """
    app_logger.info("[Scheduler] Rule 3: 3-day escalation check triggered.")
    db = SessionLocal()
    try:
        manager = _get_designated_manager(db)
        if not manager:
            app_logger.warning("[Scheduler] Rule 3: no active ceo/admin found; cannot escalate.")
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
            try:
                _escalate_one_lead(db, lead, manager, cutoff)
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                app_logger.exception(f"[Scheduler] Rule 3 failed for lead {lead.id}: {exc}")
    finally:
        db.close()


@single_instance("refresh_session_cleanup")
def cleanup_expired_refresh_sessions():
    """
    پاک‌سازی نشست‌های توکن تمدید که از انقضا+دوره‌ی نگهداری گذشته‌اند
    تا جدول refresh_sessions رشد بی‌پایان نکند.
    """
    app_logger.info("[Scheduler] refresh-session cleanup triggered.")
    from app.services.auth_service import cleanup_expired

    db = SessionLocal()
    try:
        removed = cleanup_expired(db)
        if removed:
            app_logger.info(f"[Scheduler] removed {removed} expired refresh session(s).")
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        app_logger.exception(f"[Scheduler] refresh-session cleanup failed: {exc}")
    finally:
        db.close()


@single_instance("login_rate_event_cleanup")
def cleanup_login_rate_events():
    """
    نگهداری: پاک‌سازیِ رویدادهای محدودسازِ ورود که از پنجره خارج شده‌اند
    تا جدول login_rate_events (بودجه‌ی مشترکِ brute-force) رشد بی‌پایان
    نکند — مخصوصاً روی استقرارهایی که ترافیکِ لاگینِ ناموفقِ کمی دارند و
    پاک‌سازیِ ضمنیِ داخلِ record به‌ندرت اتفاق می‌افتد.
    """
    app_logger.info("[Scheduler] login rate-event cleanup triggered.")
    from app.core.rate_limit import cleanup_login_rate_events as _cleanup

    try:
        _cleanup()
    except Exception as exc:  # noqa: BLE001
        app_logger.exception(f"[Scheduler] login rate-event cleanup failed: {exc}")


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

    # قانون ۴: هر ۵ دقیقه بررسی می‌شود که آیا سررسید پیگیریِ لیدی فرا رسیده
    scheduler.add_job(check_due_followups, 'interval', minutes=5)

    # قانون ۳: هر ساعت بررسی می‌شود که آیا پرونده‌ای ۳ روز بدون فعالیت مانده
    scheduler.add_job(escalate_stale_leads, 'interval', hours=1)

    # نگهداشت: پاک‌سازی روزانه‌ی نشست‌های تمدیدِ منقضی‌شده (ساعت ۴ صبح تهران)
    scheduler.add_job(
        cleanup_expired_refresh_sessions, 'cron', hour=4, minute=0, timezone=jalali.TEHRAN_TZ
    )

    # نگهداشت: پاک‌سازیِ ساعتیِ رویدادهای محدودسازِ ورودِ خارج از پنجره
    scheduler.add_job(cleanup_login_rate_events, 'interval', hours=1)

    scheduler.start()
    return scheduler
