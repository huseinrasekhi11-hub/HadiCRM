"""
منطق داشبورد و نمودارهای تحلیلی مدیریت
-----------------------------------------------------------
تغییر این نسخه: پشتیبانی تقویم جلالی.
  * فروش روزانه و روند فروش با پارامتر calendar= jalali
    به‌صورت واقعی بر اساس روز/هفته/ماه جلالی گروه‌بندی می‌شوند
    (تجمیع سمت سرور، نه صرفاً تبدیل رشته‌ی نمایشی).
  * رفتار پیش‌فرض (gregorian) کاملاً بدون تغییر حفظ شده است.

مبنای تاریخ «فروش»، آخرین تغییر وضعیت پرونده (status_updated_at)
است؛ این ستون به‌صورت naive و به وقت محلی تهران ذخیره می‌شود و
طبق قانون مستند در app/core/jalali.py همان‌گونه تفسیر می‌شود.
"""
from datetime import datetime, timedelta, timezone

import jdatetime
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.constants.roles import Roles
from app.core import jalali
from app.crud.lead import get_pipeline
from app.crud.notification import get_unread_count
from app.models.activity import Activity
from app.models.assignment_history import AssignmentHistory
from app.models.lead import Lead
from app.models.lead_escalation import LeadEscalation
from app.models.task import Task
from app.models.user import User
from app.schemas.lead import CLOSED_STATUSES

# وضعیت رسمی «فروش موفق»: صدور فاکتور/عامل نهایی
WON_STATUS = "final_factor"
LOST_STATUS = "closed_lost"


def _today_bounds():
    """
    کران‌های «امروز» — باید روز تقویمیِ تهران باشد، نه روز تقویمیِ UTC.
    قبلاً این تابع نیمه‌شب UTC را به‌عنوان شروع/پایانِ «امروز» محاسبه
    می‌کرد؛ چون تهران ۳٫۵ ساعت جلوتر از UTC است، حدود ۳٫۵ ساعت از هر
    شبانه‌روزِ واقعیِ تهران در «امروزِ» داشبورد دیده نمی‌شد (یا برعکس،
    بخشی از دیروز/فردا به اشتباه «امروز» حساب می‌شد) — پیگیری‌های
    امروز، وظایف امروز و... را اشتباه می‌شمرد. اینجا از همان تابعِ
    مرجعِ jalali_today_bounds_utc استفاده می‌شود که در فیلتر
    «پیگیری‌های امروز» (crud/lead.py) هم به کار رفته، تا هر دو بخش
    از یک تعریفِ «امروز» پیروی کنند.
    """
    now = datetime.now(timezone.utc)
    start, end = jalali.jalali_today_bounds_utc()
    return now, start, end


def open_leads_query(db: Session, owner_id: int | None = None):
    """پرس‌وجوی پرونده‌های باز (هر وضعیت جز برد/باخت)."""
    query = db.query(Lead).filter(
        Lead.is_deleted == False,
        Lead.status.notin_(CLOSED_STATUSES),
    )
    if owner_id is not None:
        query = query.filter(Lead.owner_id == owner_id)
    return query


def _name_map(db: Session, user_ids) -> dict[int, str]:
    """یک‌بار واکشی نام کاربران برای ساخت پاسخ‌های خوانا."""
    ids = [uid for uid in user_ids if uid is not None]
    if not ids:
        return {}
    rows = (
        db.query(User.id, User.full_name)
        .filter(User.id.in_(ids))
        .all()
    )
    return {user_id: full_name for user_id, full_name in rows}


# ==========================================================
# داشبورد کارشناس
# ==========================================================
def get_salesperson_dashboard(db: Session, current_user: User):
    now, today_start, today_end = _today_bounds()
    critical_cutoff = now - timedelta(days=14)

    my_open = open_leads_query(db, current_user.id)

    today_followups = my_open.filter(
        Lead.next_follow_up.isnot(None),
        Lead.next_follow_up >= today_start,
        Lead.next_follow_up < today_end,
    ).count()

    overdue_followups = my_open.filter(
        Lead.next_follow_up.isnot(None),
        Lead.next_follow_up < now,
    ).count()

    new_leads = my_open.filter(Lead.status == "new").count()

    critical_leads = my_open.filter(
        func.coalesce(Lead.last_contact_at, Lead.created_at) < critical_cutoff,
    ).count()

    today_tasks = (
        db.query(Task)
        .filter(
            Task.assigned_to_id == current_user.id,
            Task.is_deleted == False,
            Task.status != "done",
            Task.due_at >= today_start,
            Task.due_at < today_end,
        )
        .count()
    )

    overdue_tasks = (
        db.query(Task)
        .filter(
            Task.assigned_to_id == current_user.id,
            Task.is_deleted == False,
            Task.status != "done",
            Task.due_at < now,
        )
        .count()
    )

    activities_today = (
        db.query(Activity)
        .join(Lead, Activity.lead_id == Lead.id)
        .filter(
            Lead.owner_id == current_user.id,
            Activity.created_at >= today_start,
            Activity.created_at < today_end,
        )
        .count()
    )

    return {
        "my_leads": db.query(Lead).filter(Lead.owner_id == current_user.id).count(),
        "my_tasks": db.query(Task)
            .filter(Task.assigned_to_id == current_user.id, Task.is_deleted == False)
            .count(),
        "today_followups": today_followups,
        "overdue_followups": overdue_followups,
        "new_leads": new_leads,
        "critical_leads": critical_leads,
        "today_tasks": today_tasks,
        "overdue_tasks": overdue_tasks,
        "unread_notifications": get_unread_count(db, current_user),
        "activities_today": activities_today,
        "recent_activity_feed": _recent_activity_feed(db, owner_id=current_user.id),
        "recently_assigned": _recently_assigned(db, current_user.id),
    }


# ==========================================================
# داشبورد مدیر
# ==========================================================
def get_manager_dashboard(db: Session, current_user: User):
    now, today_start, today_end = _today_bounds()
    at_risk_cutoff = now - timedelta(days=7)

    all_open = open_leads_query(db)

    needs_attention = all_open.filter(
        func.coalesce(Lead.last_contact_at, Lead.created_at) < at_risk_cutoff,
    ).count()

    overdue_leads = all_open.filter(
        Lead.next_follow_up.isnot(None),
        Lead.next_follow_up < now,
    ).count()

    inactive_leads = all_open.filter(Lead.next_follow_up.is_(None)).count()

    escalated_leads = all_open.filter(Lead.is_escalated == True).count()

    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # ماه‌شمارِ «این ماه» برای فروش/باخت باید بر اساس تقویمِ تهران و
    # ستونِ status_updated_at باشد، نه Lead.updated_at (که با هر
    # ویرایشی — حتی یک یادداشت روی یک پرونده‌ی قدیمیِ برد/باخت‌شده —
    # تغییر می‌کند و آن پرونده را به‌اشتباه «این ماه بسته شده» نشان
    # می‌دهد) و نه با کران‌های ماهِ UTC (که تا ۳٫۵ ساعت از ابتدای/انتهای
    # ماهِ تهران را جابه‌جا می‌کند). status_updated_at ستونی naive و به
    # وقت محلی تهران است (طبق قرارداد app/core/jalali.py)، پس کرانش هم
    # باید naive و به وقت تهران باشد.
    tehran_now = jalali.naive_tehran_now()
    month_start_tehran = tehran_now.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )

    escalations_this_month = (
        db.query(LeadEscalation)
        .filter(LeadEscalation.created_at >= month_start)
        .count()
    )

    performance_rows = []
    salespeople = db.query(User).filter(
        User.role.in_([Roles.SALES, Roles.SALES_MANAGER])
    ).all()

    # N+1 fix: previously this loop ran 3 COUNT queries per salesperson
    # (3S+1 round-trips). The same numbers now come from three grouped
    # aggregates regardless of team size. Semantics are unchanged
    # (won/lost deliberately keep their original filters).
    salesperson_ids = [person.id for person in salespeople]
    open_counts = dict(
        db.query(Lead.owner_id, func.count(Lead.id))
        .filter(
            Lead.is_deleted == False,
            Lead.status.notin_(CLOSED_STATUSES),
            Lead.owner_id.in_(salesperson_ids),
        )
        .group_by(Lead.owner_id)
        .all()
    ) if salesperson_ids else {}
    won_counts = dict(
        db.query(Lead.owner_id, func.count(Lead.id))
        .filter(
            Lead.owner_id.in_(salesperson_ids),
            Lead.status == WON_STATUS,
            Lead.status_updated_at >= month_start_tehran,
        )
        .group_by(Lead.owner_id)
        .all()
    ) if salesperson_ids else {}
    lost_counts = dict(
        db.query(Lead.owner_id, func.count(Lead.id))
        .filter(
            Lead.owner_id.in_(salesperson_ids),
            Lead.status == LOST_STATUS,
            Lead.status_updated_at >= month_start_tehran,
        )
        .group_by(Lead.owner_id)
        .all()
    ) if salesperson_ids else {}

    for person in salespeople:
        performance_rows.append({
            "user_id": person.id,
            "full_name": person.full_name,
            "open_leads": open_counts.get(person.id, 0),
            "won_this_month": won_counts.get(person.id, 0),
            "lost_this_month": lost_counts.get(person.id, 0),
        })

    return {
        "users": db.query(User).count(),
        "leads": db.query(Lead).filter(Lead.is_deleted == False).count(),
        "tasks": db.query(Task).filter(Task.is_deleted == False).count(),
        "my_leads": db.query(Lead).filter(Lead.owner_id == current_user.id).count(),
        "pipeline": get_pipeline(db),
        "needs_attention": needs_attention,
        "overdue_leads": overdue_leads,
        "inactive_leads": inactive_leads,
        "escalated_leads": escalated_leads,
        "escalations_this_month": escalations_this_month,
        "salesperson_performance": performance_rows,
        "unread_notifications": get_unread_count(db, current_user),
        "recent_activity_feed": _recent_activity_feed(db),
        "recently_escalated": _recently_escalated(db),
    }


# ==========================================================
# نمودار ۱: فروش روزانه (Rial)
# پشتیبانی از تقویم جلالی و میلادی + بازه‌ی اختیاری
# ==========================================================
def get_daily_sales(
    db: Session,
    days: int = 30,
    calendar: str = "gregorian",
    date_from: datetime | None = None,
    date_to: datetime | None = None,
):
    if calendar == "jalali":
        return _daily_sales_jalali(db, days, date_from, date_to)
    return _daily_sales_gregorian(db, days, date_from, date_to)


def _won_sale_rows(db: Session):
    """سطرهای (زمان فروش، مبلغ) برای پرونده‌های فروش موفقِ حذف‌نشده."""
    return db.query(Lead.status_updated_at, Lead.sale_amount).filter(
        Lead.is_deleted == False,
        Lead.status == WON_STATUS,
        Lead.status_updated_at.isnot(None),
    )


def _daily_sales_jalali(db, days, date_from, date_to):
    """
    گروه‌بندی واقعی فروش بر اساس روز جلالی.
    ستون status_updated_at به وقت محلی تهران ذخیره شده و مستقیماً
    به تاریخ جلالی همان روز نگاشت می‌شود.
    """
    query = _won_sale_rows(db)

    zero_fill = None

    if date_from is not None or date_to is not None:
        if date_from is not None:
            query = query.filter(
                Lead.status_updated_at >= jalali.naive_tehran_from_utc(date_from)
            )
        if date_to is not None:
            # کران پایان «دقیق» است: فراگیریِ ورودی‌های فقط-تاریخ
            # (یک روز کامل) در مرز API انجام می‌شود
            # (_parse_datetime_bound با inclusive_end=True)، نه اینجا —
            # چون افزودن یک روز کامل به یک datetime صریحِ با ساعتِ مشخص،
            # ۲۴ ساعت اضافه بر بازه‌ی درخواستی کاربر شامل می‌شد.
            query = query.filter(
                Lead.status_updated_at < jalali.naive_tehran_from_utc(date_to)
            )
    else:
        today_naive = jalali.naive_tehran_now()
        today_j = jdatetime.date.fromgregorian(date=today_naive.date())
        start_j = today_j - jdatetime.timedelta(days=days - 1)
        g_start = start_j.togregorian()
        query = query.filter(
            Lead.status_updated_at >= datetime(g_start.year, g_start.month, g_start.day)
        )
        zero_fill = (days, start_j)

    rows = query.all()

    buckets: dict[str, list[int]] = {}
    for ts, amount in rows:
        if ts is None:
            continue
        j_date = jdatetime.date.fromgregorian(date=ts.date())
        key = jalali.format_jalali_label(j_date)
        aggregate = buckets.setdefault(key, [0, 0])
        aggregate[0] += int(amount or 0)
        aggregate[1] += 1

    if zero_fill is not None:
        total_days, start_j = zero_fill
        result = []
        for i in range(total_days):
            j_day = start_j + jdatetime.timedelta(days=i)
            key = jalali.format_jalali_label(j_day)
            amount, count = buckets.get(key, (0, 0))
            result.append({"label": key, "amount": amount, "count": count})
        return result

    return [
        {"label": key, "amount": value[0], "count": value[1]}
        for key, value in sorted(buckets.items())
    ]


def _daily_sales_gregorian(db, days, date_from, date_to):
    """رفتار میلادی (پیش‌فرض) — با پشتیبانی بازه‌ی اختیاری."""
    if date_from is None and date_to is None:
        # ستون status_updated_at به‌صورت naive و به وقت تهران ذخیره می‌شود؛
        # کران «امروز» هم باید روز تقویمی تهران باشد، نه UTC. پیش از این
        # نیمه‌شبِ UTC مبنا بود و ~۳٫۵ ساعت از هر شبانه‌روزِ تهران در
        # برچسب روز اشتباه می‌افتاد.
        now = jalali.naive_tehran_now()
        start = (now - timedelta(days=days - 1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        rows = (
            db.query(
                func.date(Lead.status_updated_at).label("day"),
                func.coalesce(func.sum(Lead.sale_amount), 0),
                func.count(Lead.id),
            )
            .filter(
                Lead.is_deleted == False,
                Lead.status == WON_STATUS,
                Lead.status_updated_at.isnot(None),
                Lead.status_updated_at >= start,
            )
            .group_by("day")
            .all()
        )

        by_day = {
            str(day): (int(amount or 0), count)
            for day, amount, count in rows
        }

        result = []
        for i in range(days):
            day_label = (start + timedelta(days=i)).date().isoformat()
            amount, count = by_day.get(day_label, (0, 0))
            result.append({"label": day_label, "amount": amount, "count": count})
        return result

    # حالت بازه‌ی صریح: بدون صفرگذاری، فقط سطل‌های موجود.
    # کران‌های ورودی UTC-aware هستند (تبدیل در مرز API)؛ چون ستون
    # naive و به وقت تهران است، مقایسه‌ی مستقیم با aware مرزها را به
    # اندازه‌ی اختلاف منطقه‌زمانی جابه‌جا می‌کرد — پس ابتدا به naiveِ
    # تهران تبدیل می‌شوند. فراگیریِ ورودی فقط-تاریخ در مرز API انجام شده.
    query = _won_sale_rows(db)
    if date_from is not None:
        query = query.filter(
            Lead.status_updated_at >= jalali.naive_tehran_from_utc(date_from)
        )
    if date_to is not None:
        query = query.filter(
            Lead.status_updated_at < jalali.naive_tehran_from_utc(date_to)
        )

    rows = (
        query.with_entities(
            func.date(Lead.status_updated_at).label("day"),
            func.coalesce(func.sum(Lead.sale_amount), 0),
            func.count(Lead.id),
        )
        .group_by("day")
        .order_by("day")
        .all()
    )

    return [
        {"label": str(day), "amount": int(amount or 0), "count": count}
        for day, amount, count in rows
    ]


# ==========================================================
# نمودار ۲: مبلغ فروش / تعداد برد / میانگین هر کارشناس (Rial)
# ==========================================================
def get_sales_by_user(db: Session, days: int | None = None):
    cutoff = None
    if days is not None:
        # status_updated_at naive و به وقت تهران است؛ cutoff هم باید
        # همان مبنا باشد (نه UTC-aware).
        cutoff = jalali.naive_tehran_now() - timedelta(days=days)

    filters = [
        Lead.is_deleted == False,
        Lead.status == WON_STATUS,
        Lead.status_updated_at.isnot(None),
    ]
    if cutoff is not None:
        filters.append(Lead.status_updated_at >= cutoff)

    rows = (
        db.query(
            Lead.owner_id,
            func.count(Lead.id),
            func.coalesce(func.sum(Lead.sale_amount), 0),
        )
        .filter(*filters)
        .group_by(Lead.owner_id)
        .all()
    )
    stats = {
        owner_id: (count, int(total or 0))
        for owner_id, count, total in rows
    }

    salespeople = (
        db.query(User)
        .filter(
            User.role.in_([Roles.SALES, Roles.SALES_MANAGER]),
            User.is_active == True,
        )
        .order_by(User.full_name)
        .all()
    )

    covered_ids: set[int] = set()
    result = []
    for person in salespeople:
        covered_ids.add(person.id)
        won_count, total_sales = stats.get(person.id, (0, 0))
        result.append(
            {
                "user_id": person.id,
                "full_name": person.full_name,
                "won_count": won_count,
                "total_sales": total_sales,
                "average_sale": int(total_sales / won_count) if won_count else 0,
            }
        )

    extra_ids = [uid for uid in stats.keys() if uid not in covered_ids]
    if extra_ids:
        extra_names = _name_map(db, extra_ids)
        for uid in extra_ids:
            won_count, total_sales = stats[uid]
            result.append(
                {
                    "user_id": uid,
                    "full_name": extra_names.get(uid),
                    "won_count": won_count,
                    "total_sales": total_sales,
                    "average_sale": int(total_sales / won_count) if won_count else 0,
                }
            )

    result.sort(key=lambda row: row["total_sales"], reverse=True)
    return result


# ==========================================================
# نمودار ۳: توزیع پرونده‌ها به تفکیک کاربر
# ==========================================================
def get_leads_by_user(db: Session):
    rows = (
        db.query(
            Lead.owner_id,
            func.count(Lead.id),
            func.coalesce(
                func.sum(case((Lead.status.notin_(CLOSED_STATUSES), 1), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(case((Lead.status == WON_STATUS, 1), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(case((Lead.status == LOST_STATUS, 1), else_=0)),
                0,
            ),
        )
        .filter(Lead.is_deleted == False)
        .group_by(Lead.owner_id)
        .all()
    )

    names = _name_map(db, [owner_id for owner_id, *_ in rows])

    result = [
        {
            "user_id": owner_id,
            "full_name": names.get(owner_id),
            "total_leads": int(total or 0),
            "open_leads": int(open_count or 0),
            "won_leads": int(won_count or 0),
            "lost_leads": int(lost_count or 0),
        }
        for owner_id, total, open_count, won_count, lost_count in rows
    ]
    result.sort(key=lambda row: row["total_leads"], reverse=True)
    return result


# ==========================================================
# نمودار ۴: آمار کلان قیف و نرخ تبدیل
# ==========================================================
def get_conversion_stats(db: Session):
    total, open_count, won_count, lost_count = (
        db.query(
            func.count(Lead.id),
            func.coalesce(
                func.sum(case((Lead.status.notin_(CLOSED_STATUSES), 1), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(case((Lead.status == WON_STATUS, 1), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(case((Lead.status == LOST_STATUS, 1), else_=0)),
                0,
            ),
        )
        .filter(Lead.is_deleted == False)
        .one()
    )

    total = int(total or 0)
    open_count = int(open_count or 0)
    won_count = int(won_count or 0)
    lost_count = int(lost_count or 0)

    closed = won_count + lost_count
    conversion_rate = round((won_count / closed) * 100, 2) if closed else 0.0

    return {
        "total_leads": total,
        "open_leads": open_count,
        "won_leads": won_count,
        "lost_leads": lost_count,
        "conversion_rate": conversion_rate,
    }


# ==========================================================
# نمودار ۵: بیشترین ارجاع‌های دریافت‌شده
# ==========================================================
def get_referrals_received(db: Session):
    """ارجاع‌های واقعی (خود-ارجاعیِ اولیه حذف شده است)."""
    rows = (
        db.query(
            AssignmentHistory.assigned_to_id,
            func.count(AssignmentHistory.id),
        )
        .filter(
            AssignmentHistory.assigned_by_id != AssignmentHistory.assigned_to_id
        )
        .group_by(AssignmentHistory.assigned_to_id)
        .order_by(func.count(AssignmentHistory.id).desc())
        .all()
    )

    names = _name_map(db, [to_id for to_id, _ in rows])

    return [
        {
            "user_id": to_id,
            "full_name": names.get(to_id),
            "received_count": int(count or 0),
        }
        for to_id, count in rows
    ]


# ==========================================================
# نمودار ۶: تعداد ارجاع‌ها بین کاربران (از → به)
# ==========================================================
def get_referrals_between_users(db: Session):
    rows = (
        db.query(
            AssignmentHistory.assigned_by_id,
            AssignmentHistory.assigned_to_id,
            func.count(AssignmentHistory.id),
        )
        .filter(
            AssignmentHistory.assigned_by_id != AssignmentHistory.assigned_to_id
        )
        .group_by(
            AssignmentHistory.assigned_by_id,
            AssignmentHistory.assigned_to_id,
        )
        .order_by(func.count(AssignmentHistory.id).desc())
        .all()
    )

    names = _name_map(
        db,
        {from_id for from_id, _, _ in rows} | {to_id for _, to_id, _ in rows},
    )

    return [
        {
            "from_user_id": from_id,
            "from_full_name": names.get(from_id),
            "to_user_id": to_id,
            "to_full_name": names.get(to_id),
            "count": int(count or 0),
        }
        for from_id, to_id, count in rows
    ]


# ==========================================================
# نمودار ۷: روند فروش در زمان
# میلادی: روز/هفته/ماه با date_trunc
# جلالی: روز/هفته(شنبه‌مبنا)/ماه با تجمیع واقعی جلالی
# ==========================================================
def get_sales_trend(
    db: Session,
    days: int = 90,
    granularity: str = "day",
    calendar: str = "gregorian",
):
    if calendar == "jalali":
        return _sales_trend_jalali(db, days, granularity)

    unit = granularity if granularity in ("day", "week", "month") else "day"
    # date_trunc روی ستون naive تهران، سطل‌های روز/هفته/ماه تهران می‌سازد؛
    # کران پنجره هم باید با همان مبنا باشد (پیش از این cutoff آگاهِ UTC با
    # ستون naive مقایسه می‌شد).
    start = jalali.naive_tehran_now() - timedelta(days=days)

    period = func.date_trunc(unit, Lead.status_updated_at).label("period")

    rows = (
        db.query(
            period,
            func.coalesce(func.sum(Lead.sale_amount), 0),
            func.count(Lead.id),
        )
        .filter(
            Lead.is_deleted == False,
            Lead.status == WON_STATUS,
            Lead.status_updated_at.isnot(None),
            Lead.status_updated_at >= start,
        )
        .group_by(period)
        .order_by(period.asc())
        .all()
    )

    return [
        {
            "label": period_value.date().isoformat(),
            "amount": int(amount or 0),
            "count": int(count or 0),
        }
        for period_value, amount, count in rows
        if period_value is not None
    ]


def _sales_trend_jalali(db, days, granularity):
    """
    روند فروش با دانه‌بندی جلالی:
      day   -> برچسب روز جلالی 1405/05/01
      week  -> برچسب شنبه‌ی شروع هفته‌ی ایرانی
      month -> برچسب ماه جلالی 1405/05
    """
    unit = granularity if granularity in ("day", "week", "month") else "day"
    cutoff = jalali.naive_tehran_now() - timedelta(days=days)

    rows = (
        _won_sale_rows(db)
        .filter(Lead.status_updated_at >= cutoff)
        .all()
    )

    buckets: dict[str, list[int]] = {}
    for ts, amount in rows:
        if ts is None:
            continue
        j_date = jdatetime.date.fromgregorian(date=ts.date())

        if unit == "month":
            key = f"{j_date.year:04d}/{j_date.month:02d}"
        elif unit == "week":
            week_start = jalali.jalali_week_start(j_date)
            key = jalali.format_jalali_label(week_start)
        else:
            key = jalali.format_jalali_label(j_date)

        aggregate = buckets.setdefault(key, [0, 0])
        aggregate[0] += int(amount or 0)
        aggregate[1] += 1

    return [
        {"label": key, "amount": value[0], "count": value[1]}
        for key, value in sorted(buckets.items())
    ]


# ==========================================================
# فیدهای عملیاتی (بدون تغییر نسبت به قبل)
# ==========================================================
def _recent_activity_feed(db: Session, owner_id: int | None = None, limit: int = 8):
    query = db.query(Activity, Lead.customer_name).join(
        Lead, Activity.lead_id == Lead.id
    )
    if owner_id is not None:
        query = query.filter(Lead.owner_id == owner_id)

    rows = query.order_by(Activity.created_at.desc()).limit(limit).all()

    return [
        {
            "id": activity.id,
            "lead_id": activity.lead_id,
            "customer_name": customer_name,
            "activity_type": activity.activity_type,
            "title": activity.title,
            "created_at": activity.created_at,
        }
        for activity, customer_name in rows
    ]


def _recently_assigned(db: Session, user_id: int, limit: int = 5):
    rows = (
        db.query(AssignmentHistory, Lead.customer_name)
        .join(Lead, AssignmentHistory.lead_id == Lead.id)
        .filter(AssignmentHistory.assigned_to_id == user_id)
        .order_by(AssignmentHistory.assigned_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "lead_id": history.lead_id,
            "customer_name": customer_name,
            "assigned_at": history.assigned_at,
        }
        for history, customer_name in rows
    ]


def _recently_escalated(db: Session, limit: int = 5):
    rows = (
        db.query(LeadEscalation, Lead.customer_name)
        .join(Lead, LeadEscalation.lead_id == Lead.id)
        .order_by(LeadEscalation.created_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "lead_id": escalation.lead_id,
            "customer_name": customer_name,
            "created_at": escalation.created_at,
        }
        for escalation, customer_name in rows
    ]
