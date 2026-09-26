"""
Regression tests for app/scheduler/jobs.py business-rule bugs.

Unlike most of this suite, these call the job functions directly against
the database rather than going through the HTTP API, since the jobs
themselves are not exposed as endpoints. They still require the same
database as the rest of the suite (PostgreSQL via DATABASE_URL, admin
user seeded, migrations applied).
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.database.database import SessionLocal
from app.models.lead import Lead
from app.models.user import User
from app.scheduler.jobs import (
    check_no_contact_reminders,
    escalate_stale_leads,
    send_daily_morning_reminders,
)


def unique_mobile():
    return f"0912{str(uuid4().int)[:7]}"


def _get_admin(db):
    admin = db.query(User).filter(User.mobile == "09120000000").first()
    assert admin is not None, "seeded admin user (09120000000) must exist"
    return admin


def test_sla_notified_is_set_when_contact_was_made_in_time():
    """
    Regression test: when a rep DID contact the lead after assignment
    (has_contact_since_assignment is True), the no-contact-reminder job
    must still mark sla_notified True. Previously it only set the flag
    on the "send a reminder" path and skipped it entirely on the
    "already contacted, nothing to do" path via a bare `continue` —
    leaving contacted leads permanently eligible to be re-evaluated by
    the query on every single run of this job.
    """
    db = SessionLocal()
    try:
        admin = _get_admin(db)
        lead = Lead(
            customer_name="Scheduler Regression - Contacted In Time",
            mobile=unique_mobile(),
            mobile_normalized=unique_mobile(),
            source="test",
            need="test",
            status="contacted",
            owner_id=admin.id,
            created_by_id=admin.id,
            last_assigned_at=datetime.now(timezone.utc) - timedelta(minutes=90),
            last_contact_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            sla_notified=False,
        )
        db.add(lead)
        db.commit()
        db.refresh(lead)
        lead_id = lead.id
    finally:
        db.close()

    check_no_contact_reminders()

    db2 = SessionLocal()
    try:
        lead_after = db2.query(Lead).filter(Lead.id == lead_id).first()
        assert lead_after.sla_notified is True, (
            "a lead that was contacted in time must be marked sla_notified "
            "so it stops being re-evaluated by this job forever"
        )
    finally:
        db2.close()


def test_escalation_does_not_immediately_reclaim_freshly_reassigned_lead():
    """
    Regression test: escalate_stale_leads must account for a recent
    reassignment, not just created_at/last_contact_at. Previously an
    old, never-contacted lead that was reassigned to a new rep moments
    ago could be immediately escalated away from that rep on the very
    next scheduler run, because `last_activity` only ever fell back to
    created_at and never considered last_assigned_at.
    """
    db = SessionLocal()
    try:
        admin = _get_admin(db)
        rep_mobile = unique_mobile()
        rep = User(
            full_name="Scheduler Regression Fresh Rep",
            mobile=rep_mobile,
            password=admin.password,
            role="sales",
            is_active=True,
        )
        db.add(rep)
        db.commit()
        db.refresh(rep)

        lead = Lead(
            customer_name="Scheduler Regression - Freshly Reassigned",
            mobile=unique_mobile(),
            mobile_normalized=unique_mobile(),
            source="test",
            need="test",
            status="contacted",
            owner_id=rep.id,
            created_by_id=admin.id,
            created_at=datetime.now(timezone.utc) - timedelta(days=4),
            last_assigned_at=datetime.now(timezone.utc) - timedelta(minutes=2),
            last_contact_at=None,
            is_escalated=False,
            sla_notified=False,
        )
        db.add(lead)
        db.commit()
        db.refresh(lead)
        lead_id = lead.id
        rep_id = rep.id
    finally:
        db.close()

    escalate_stale_leads()

    db2 = SessionLocal()
    try:
        lead_after = db2.query(Lead).filter(Lead.id == lead_id).first()
        assert lead_after.is_escalated is False, (
            "a lead reassigned only 2 minutes ago must not be immediately "
            "escalated away, even if the lead itself is old"
        )
        assert lead_after.owner_id == rep_id
    finally:
        db2.close()


def test_escalation_still_fires_for_a_lead_with_no_recent_activity_or_assignment():
    """
    Sanity check for the fix above: a genuinely stale lead — old,
    never contacted, AND not recently (re)assigned — must still be
    escalated. The fix must not disable escalation altogether.
    """
    db = SessionLocal()
    try:
        admin = _get_admin(db)
        rep_mobile = unique_mobile()
        rep = User(
            full_name="Scheduler Regression Stale Rep",
            mobile=rep_mobile,
            password=admin.password,
            role="sales",
            is_active=True,
        )
        db.add(rep)
        db.commit()
        db.refresh(rep)

        lead = Lead(
            customer_name="Scheduler Regression - Genuinely Stale",
            mobile=unique_mobile(),
            mobile_normalized=unique_mobile(),
            source="test",
            need="test",
            status="contacted",
            owner_id=rep.id,
            created_by_id=admin.id,
            created_at=datetime.now(timezone.utc) - timedelta(days=10),
            last_assigned_at=datetime.now(timezone.utc) - timedelta(days=10),
            last_contact_at=None,
            is_escalated=False,
            sla_notified=False,
        )
        db.add(lead)
        db.commit()
        db.refresh(lead)
        lead_id = lead.id
    finally:
        db.close()

    escalate_stale_leads()

    db2 = SessionLocal()
    try:
        lead_after = db2.query(Lead).filter(Lead.id == lead_id).first()
        assert lead_after.is_escalated is True
    finally:
        db2.close()


def test_won_this_month_uses_status_updated_at_not_updated_at():
    """
    Regression test: get_manager_dashboard's "won_this_month" figure
    must be based on Lead.status_updated_at (when the lead actually
    became final_factor), not Lead.updated_at (which changes on any
    edit at all, via the column's onupdate). Previously an old win,
    touched by an unrelated later edit (e.g. adding a note), would
    have its updated_at bumped to "now" and get miscounted as a fresh
    win for the current month.
    """
    from app.core.jalali import naive_tehran_now
    from app.crud.dashboard import get_manager_dashboard

    db = SessionLocal()
    try:
        admin = _get_admin(db)
        rep = User(
            full_name="Won-This-Month Regression Rep",
            mobile=unique_mobile(),
            password=admin.password,
            role="sales",
            is_active=True,
        )
        db.add(rep)
        db.commit()
        db.refresh(rep)

        # Won six months ago.
        old_lead = Lead(
            customer_name="Old Win Touched Recently",
            mobile=unique_mobile(),
            mobile_normalized=unique_mobile(),
            source="test",
            need="test",
            status="final_factor",
            owner_id=rep.id,
            created_by_id=admin.id,
            status_updated_at=naive_tehran_now() - timedelta(days=180),
        )
        db.add(old_lead)
        db.commit()
        db.refresh(old_lead)

        # An unrelated later edit bumps updated_at (via onupdate) without
        # touching status_updated_at at all.
        old_lead.resolution_notes = "unrelated note added long after the win"
        db.commit()

        # A genuine, fresh win this month, for comparison.
        fresh_lead = Lead(
            customer_name="Genuinely Recent Win",
            mobile=unique_mobile(),
            mobile_normalized=unique_mobile(),
            source="test",
            need="test",
            status="final_factor",
            owner_id=rep.id,
            created_by_id=admin.id,
            status_updated_at=naive_tehran_now(),
        )
        db.add(fresh_lead)
        db.commit()

        dashboard = get_manager_dashboard(db, admin)
        row = next(
            r for r in dashboard["salesperson_performance"] if r["user_id"] == rep.id
        )
        assert row["won_this_month"] == 1, (
            "only the genuinely-recent win should count; the old win "
            "touched by an unrelated edit must not be counted just "
            "because Lead.updated_at was bumped"
        )
    finally:
        db.close()


def test_daily_reminder_cron_job_is_anchored_to_tehran_timezone():
    """
    Regression test: the daily-morning-reminder cron job must be
    anchored to Asia/Tehran, not whatever timezone the server process
    happens to run in. Previously scheduler.add_job(..., 'cron',
    hour=8, minute=0) was registered with no explicit timezone, so
    APScheduler used the server's local timezone by default. On a
    server running in UTC (the common case for cloud deployments,
    and the case in this test environment), "8 AM" actually fired at
    11:30 AM Tehran time instead of 8:00 AM as the business rule
    intends.
    """
    from app.core import jalali
    from app.scheduler.jobs import start_scheduler

    scheduler = start_scheduler()
    try:
        job = next(
            j for j in scheduler.get_jobs()
            if j.func is send_daily_morning_reminders
        )
        assert str(job.trigger.timezone) == "Asia/Tehran"

        next_run_tehran = job.next_run_time.astimezone(jalali.TEHRAN_TZ)
        assert (next_run_tehran.hour, next_run_tehran.minute) == (8, 0), (
            f"job's next run is {next_run_tehran} Tehran time, expected "
            "08:00 — it looks anchored to a different timezone than "
            "Asia/Tehran"
        )
    finally:
        scheduler.shutdown(wait=False)
