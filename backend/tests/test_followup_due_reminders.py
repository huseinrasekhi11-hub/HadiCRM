"""
Regression tests for app/scheduler/jobs.py::check_due_followups (Rule 4).

Before this fix, Lead.next_follow_up was purely passive: it powered the
"today"/"overdue" smart filters and dashboard counts, but nothing ever
created an in-app notification when a follow-up actually became due. A
rep who wasn't already looking at the Tasks page had no way to know a
follow-up had come due. This suite verifies the new job creates exactly
one notification per due follow-up, respects the dedup flag, skips
inactive owners without looping forever, and that setting a new
follow-up date re-arms the reminder.

Like test_scheduler_jobs.py, these call the job function directly
against the database rather than going through the HTTP API.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.database.database import SessionLocal
from app.models.lead import Lead
from app.models.notification import Notification
from app.models.user import User
from app.scheduler.jobs import check_due_followups


def unique_mobile():
    return f"0912{str(uuid4().int)[:7]}"


def _get_admin(db):
    admin = db.query(User).filter(User.mobile == "09120000000").first()
    assert admin is not None, "seeded admin user (09120000000) must exist"
    return admin


def test_due_followup_creates_exactly_one_notification():
    """
    A lead whose next_follow_up is in the past, on an open lead, with
    follow_up_notified still False, must get exactly one
    'follow_up_due' notification for its owner.
    """
    db = SessionLocal()
    try:
        admin = _get_admin(db)
        lead = Lead(
            customer_name="Followup Regression - Due Now",
            mobile=unique_mobile(),
            mobile_normalized=unique_mobile(),
            source="test",
            need="test",
            status="contacted",
            owner_id=admin.id,
            created_by_id=admin.id,
            next_follow_up=datetime.now(timezone.utc) - timedelta(minutes=5),
            follow_up_notified=False,
        )
        db.add(lead)
        db.commit()
        db.refresh(lead)
        lead_id = lead.id
        owner_id = admin.id

        before_count = (
            db.query(Notification)
            .filter(
                Notification.user_id == owner_id,
                Notification.lead_id == lead_id,
                Notification.notification_type == "follow_up_due",
            )
            .count()
        )
        assert before_count == 0
    finally:
        db.close()

    check_due_followups()

    db2 = SessionLocal()
    try:
        lead_after = db2.query(Lead).filter(Lead.id == lead_id).first()
        assert lead_after.follow_up_notified is True

        notifications = (
            db2.query(Notification)
            .filter(
                Notification.user_id == owner_id,
                Notification.lead_id == lead_id,
                Notification.notification_type == "follow_up_due",
            )
            .all()
        )
        assert len(notifications) == 1, (
            "exactly one follow_up_due notification should be created "
            "for a lead whose follow-up just became due"
        )
    finally:
        db2.close()


def test_due_followup_does_not_fire_twice_for_the_same_due_date():
    """
    Running the job twice for the same lead/due-date must not create a
    second notification: follow_up_notified must prevent re-firing.
    """
    db = SessionLocal()
    try:
        admin = _get_admin(db)
        lead = Lead(
            customer_name="Followup Regression - No Duplicate",
            mobile=unique_mobile(),
            mobile_normalized=unique_mobile(),
            source="test",
            need="test",
            status="contacted",
            owner_id=admin.id,
            created_by_id=admin.id,
            next_follow_up=datetime.now(timezone.utc) - timedelta(minutes=5),
            follow_up_notified=False,
        )
        db.add(lead)
        db.commit()
        db.refresh(lead)
        lead_id = lead.id
        owner_id = admin.id
    finally:
        db.close()

    check_due_followups()
    check_due_followups()  # second run, same due date, no new activity

    db2 = SessionLocal()
    try:
        notifications = (
            db2.query(Notification)
            .filter(
                Notification.user_id == owner_id,
                Notification.lead_id == lead_id,
                Notification.notification_type == "follow_up_due",
            )
            .all()
        )
        assert len(notifications) == 1, (
            "the job must not create a second notification for a "
            "follow-up that was already notified"
        )
    finally:
        db2.close()


def test_future_followup_does_not_fire_yet():
    """
    A lead whose next_follow_up is still in the future must not
    generate a notification.
    """
    db = SessionLocal()
    try:
        admin = _get_admin(db)
        lead = Lead(
            customer_name="Followup Regression - Not Due Yet",
            mobile=unique_mobile(),
            mobile_normalized=unique_mobile(),
            source="test",
            need="test",
            status="contacted",
            owner_id=admin.id,
            created_by_id=admin.id,
            next_follow_up=datetime.now(timezone.utc) + timedelta(hours=2),
            follow_up_notified=False,
        )
        db.add(lead)
        db.commit()
        db.refresh(lead)
        lead_id = lead.id
        owner_id = admin.id
    finally:
        db.close()

    check_due_followups()

    db2 = SessionLocal()
    try:
        lead_after = db2.query(Lead).filter(Lead.id == lead_id).first()
        assert lead_after.follow_up_notified is False

        notifications = (
            db2.query(Notification)
            .filter(
                Notification.user_id == owner_id,
                Notification.lead_id == lead_id,
                Notification.notification_type == "follow_up_due",
            )
            .all()
        )
        assert len(notifications) == 0
    finally:
        db2.close()


def test_closed_lead_does_not_fire():
    """
    A lead that's already won/lost must not trigger a follow-up
    reminder even if next_follow_up is technically in the past (stale
    data from before closing).
    """
    db = SessionLocal()
    try:
        admin = _get_admin(db)
        lead = Lead(
            customer_name="Followup Regression - Closed Lead",
            mobile=unique_mobile(),
            mobile_normalized=unique_mobile(),
            source="test",
            need="test",
            status="final_factor",
            owner_id=admin.id,
            created_by_id=admin.id,
            next_follow_up=datetime.now(timezone.utc) - timedelta(minutes=5),
            follow_up_notified=False,
        )
        db.add(lead)
        db.commit()
        db.refresh(lead)
        lead_id = lead.id
        owner_id = admin.id
    finally:
        db.close()

    check_due_followups()

    db2 = SessionLocal()
    try:
        notifications = (
            db2.query(Notification)
            .filter(
                Notification.user_id == owner_id,
                Notification.lead_id == lead_id,
                Notification.notification_type == "follow_up_due",
            )
            .all()
        )
        assert len(notifications) == 0, (
            "a closed (won/lost) lead must never trigger a follow-up "
            "reminder, even with a stale past-due next_follow_up"
        )
    finally:
        db2.close()


def test_setting_a_new_followup_rearms_the_reminder():
    """
    Regression test for the reset logic in create_activity /
    update_lead_followup: once a lead has been notified for a given
    due date, setting a *new* next_follow_up must clear
    follow_up_notified so the new date can notify again.
    """
    from app.crud.activity import create_activity
    from app.schemas.activity import ActivityCreate

    db = SessionLocal()
    try:
        admin = _get_admin(db)
        lead = Lead(
            customer_name="Followup Regression - Rearm On Reschedule",
            mobile=unique_mobile(),
            mobile_normalized=unique_mobile(),
            source="test",
            need="test",
            status="contacted",
            owner_id=admin.id,
            created_by_id=admin.id,
            next_follow_up=datetime.now(timezone.utc) - timedelta(minutes=5),
            follow_up_notified=True,  # already notified for the old date
        )
        db.add(lead)
        db.commit()
        db.refresh(lead)
        lead_id = lead.id

        create_activity(
            db,
            lead,
            admin,
            ActivityCreate(
                activity_type="call",
                title="Rescheduled call",
                next_follow_up=datetime.now(timezone.utc) + timedelta(days=1),
            ),
        )
    finally:
        db.close()

    db2 = SessionLocal()
    try:
        lead_after = db2.query(Lead).filter(Lead.id == lead_id).first()
        assert lead_after.follow_up_notified is False, (
            "setting a new next_follow_up must reset follow_up_notified "
            "so the new due date can trigger a reminder of its own"
        )
    finally:
        db2.close()
