"""
Integration tests for the unified admin lead timeline.

Prerequisites (same as the rest of the suite):
  * PostgreSQL reachable via DATABASE_URL
  * Admin user exists: mobile 09120000000 / password Admin123!
  * Migrations applied: alembic upgrade head
"""
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def login(mobile: str, password: str):
    response = client.post(
        "/auth/login",
        data={"username": mobile, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def get_admin_headers():
    return login("09120000000", "Admin123!")


def unique_mobile():
    return f"0912{str(uuid4().int)[:7]}"


def create_sales_user(headers):
    mobile = unique_mobile()
    password = "SalesPass123!"
    response = client.post(
        "/users/",
        json={
            "full_name": "Timeline Test Salesperson",
            "mobile": mobile,
            "password": password,
            "role": "sales",
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json(), mobile, password


def build_full_lifecycle_lead(headers, sales_user_id):
    """
    ساخت یک پرونده و ثبت رویدادهای کامل روی آن:
    فعالیت دستی، تغییر وضعیت، ایجاد/اتمام وظیفه، ارجاع، فایل ضمیمه.
    """
    mobile = unique_mobile()
    create_response = client.post(
        "/leads/",
        json={
            "customer_name": "Full Lifecycle Customer",
            "mobile": mobile,
            "source": "site",
            "need": "Full lifecycle test",
        },
        headers=headers,
    )
    assert create_response.status_code == 201
    lead = create_response.json()

    # فعالیت دستی (تماس) با پیگیری بعدی
    followup_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    activity_response = client.post(
        f"/leads/{lead['id']}/activities",
        json={
            "activity_type": "call",
            "title": "First call",
            "description": "Customer answered.",
            "next_follow_up": followup_at,
        },
        headers=headers,
    )
    assert activity_response.status_code == 201

    # تغییر وضعیت
    status_response = client.patch(
        f"/leads/{lead['id']}/status",
        json={"status": "contacted"},
        headers=headers,
    )
    assert status_response.status_code == 200

    # ایجاد وظیفه
    due_at = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    task_response = client.post(
        f"/leads/{lead['id']}/tasks",
        json={
            "title": "Send catalog",
            "description": None,
            "due_at": due_at,
        },
        headers=headers,
    )
    assert task_response.status_code == 201
    task_id = task_response.json()["id"]

    # اتمام وظیفه
    complete_response = client.patch(
        f"/leads/{lead['id']}/tasks/{task_id}/status",
        json={"status": "done"},
        headers=headers,
    )
    assert complete_response.status_code == 200

    # ارجاع به کاربر فروش
    assign_response = client.patch(
        f"/leads/{lead['id']}/assign",
        json={"owner_id": sales_user_id, "note": "ارجاع تستی برای تایم‌لاین"},
        headers=headers,
    )
    assert assign_response.status_code == 200

    # بارگذاری فایل ضمیمه
    upload_response = client.post(
        f"/leads/{lead['id']}/attachments",
        files={"file": ("timeline_test.txt", b"timeline attachment", "text/plain")},
        headers=headers,
    )
    assert upload_response.status_code == 201

    return lead, mobile


def test_admin_timeline_contains_full_lifecycle():
    admin_headers = get_admin_headers()
    sales_user, _, _ = create_sales_user(admin_headers)
    lead, mobile = build_full_lifecycle_lead(admin_headers, sales_user["id"])

    response = client.get(f"/admin/leads/{lead['id']}/timeline", headers=admin_headers)
    assert response.status_code == 200

    body = response.json()
    assert body["lead_id"] == lead["id"]
    assert body["customer_name"] == "Full Lifecycle Customer"
    assert body["mobile"] == mobile
    assert body["status"] == "contacted"
    assert body["is_deleted"] is False
    assert body["owner_id"] == sales_user["id"]
    assert body["owner_full_name"] == "Timeline Test Salesperson"

    event_types = [event["event_type"] for event in body["events"]]
    assert "lead_created" in event_types
    assert "call" in event_types
    assert "status_change" in event_types
    assert "task_created" in event_types
    assert "task_completed" in event_types
    assert "lead_assigned" in event_types
    assert "attachment_uploaded" in event_types


def test_admin_timeline_assignment_event_is_enriched():
    admin_headers = get_admin_headers()
    sales_user, _, _ = create_sales_user(admin_headers)
    lead, _ = build_full_lifecycle_lead(admin_headers, sales_user["id"])

    body = client.get(f"/admin/leads/{lead['id']}/timeline", headers=admin_headers).json()

    assignment_events = [
        event for event in body["events"]
        if event["event_type"] == "lead_assigned" and event["source"] == "activity"
    ]
    assert assignment_events, "No enriched assignment activity found"

    enriched = assignment_events[0]
    assert enriched["metadata"]["assignment"]["assigned_to_id"] == sales_user["id"]
    assert enriched["metadata"]["assignment"]["assigned_to_name"] == "Timeline Test Salesperson"
    assert enriched["metadata"]["assignment"]["note"] == "ارجاع تستی برای تایم‌لاین"


def test_admin_timeline_events_sorted_newest_first():
    admin_headers = get_admin_headers()
    sales_user, _, _ = create_sales_user(admin_headers)
    lead, _ = build_full_lifecycle_lead(admin_headers, sales_user["id"])

    body = client.get(f"/admin/leads/{lead['id']}/timeline", headers=admin_headers).json()
    timestamps = [event["occurred_at"] for event in body["events"]]
    assert timestamps == sorted(timestamps, reverse=True)


def test_admin_timeline_works_for_deleted_lead():
    admin_headers = get_admin_headers()
    sales_user, _, _ = create_sales_user(admin_headers)
    lead, _ = build_full_lifecycle_lead(admin_headers, sales_user["id"])

    delete_response = client.delete(f"/leads/{lead['id']}", headers=admin_headers)
    assert delete_response.status_code == 200

    # اندپوینت معمولی دیگر دسترسی ندارد
    assert client.get(f"/leads/{lead['id']}", headers=admin_headers).status_code == 404

    # تایم‌لاین مدیریتی همچنان تاریخچه‌ی کامل را نشان می‌دهد
    response = client.get(f"/admin/leads/{lead['id']}/timeline", headers=admin_headers)
    assert response.status_code == 200

    body = response.json()
    assert body["is_deleted"] is True
    assert body["deleted_at"] is not None

    event_types = [event["event_type"] for event in body["events"]]
    assert "lead_deleted" in event_types

    # رویداد حذف باید متادیتای ممیزی داشته باشد
    deletion_event = [
        event for event in body["events"] if event["event_type"] == "lead_deleted"
    ][0]
    assert deletion_event["metadata"]["deletion_audit"]["previous_status"] == "contacted"
    assert deletion_event["metadata"]["deletion_audit"]["deleted_by_name"] == "System Administrator"


def test_admin_timeline_shows_restore_after_deletion():
    admin_headers = get_admin_headers()
    sales_user, _, _ = create_sales_user(admin_headers)
    lead, mobile = build_full_lifecycle_lead(admin_headers, sales_user["id"])

    client.delete(f"/leads/{lead['id']}", headers=admin_headers)

    # پیدا کردن رکورد ممیزی و احیا
    listing = client.get(
        "/deleted-leads/",
        params={"search": mobile},
        headers=admin_headers,
    ).json()
    audit_id = [item for item in listing if item["lead_id"] == lead["id"]][0]["id"]

    restore_response = client.post(
        f"/deleted-leads/{audit_id}/restore",
        headers=admin_headers,
    )
    assert restore_response.status_code == 200

    body = client.get(f"/admin/leads/{lead['id']}/timeline", headers=admin_headers).json()
    event_types = [event["event_type"] for event in body["events"]]
    assert "lead_deleted" in event_types
    assert "lead_restored" in event_types

    restore_event = [
        event for event in body["events"] if event["event_type"] == "lead_restored"
    ][0]
    assert restore_event["metadata"]["restoration"]["restored_by_name"] == "System Administrator"


def test_admin_timeline_shows_duplicate_submissions():
    admin_headers = get_admin_headers()
    mobile = unique_mobile()

    lead = client.post(
        "/leads/",
        json={
            "customer_name": "Duplicate Timeline Customer",
            "mobile": mobile,
            "source": "site",
            "need": None,
        },
        headers=admin_headers,
    ).json()

    # ثبت تکراری
    duplicate_response = client.post(
        "/leads/",
        json={
            "customer_name": "Duplicate Timeline Customer",
            "mobile": mobile,
            "source": "instagram",
            "need": "Second submission",
        },
        headers=admin_headers,
    )
    assert duplicate_response.json()["id"] == lead["id"]

    body = client.get(f"/admin/leads/{lead['id']}/timeline", headers=admin_headers).json()
    assert body["duplicate_count"] == 1

    event_types = [event["event_type"] for event in body["events"]]
    assert "duplicate_detected" in event_types


def test_admin_timeline_requires_admin_role():
    admin_headers = get_admin_headers()
    sales_user, mobile, password = create_sales_user(admin_headers)
    sales_headers = login(mobile, password)

    lead = client.post(
        "/leads/",
        json={
            "customer_name": "Permission Check Lead",
            "mobile": unique_mobile(),
            "source": "site",
            "need": None,
        },
        headers=sales_headers,
    ).json()

    # بدون توکن
    assert client.get(f"/admin/leads/{lead['id']}/timeline").status_code == 401
    # کاربر فروش -> 403
    assert (
        client.get(f"/admin/leads/{lead['id']}/timeline", headers=sales_headers).status_code
        == 403
    )


def test_admin_timeline_missing_lead_returns_404():
    admin_headers = get_admin_headers()
    assert (
        client.get("/admin/leads/99999999/timeline", headers=admin_headers).status_code
        == 404
    )
