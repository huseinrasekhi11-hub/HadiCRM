from datetime import datetime
from datetime import timedelta
from datetime import timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def get_admin_headers():
    response = client.post(
        "/auth/login",
        data={"username": "09120000000", "password": "Admin123!"},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]

    return {"Authorization": f"Bearer {token}"}


def create_lead(headers):
    mobile = f"0912{str(uuid4().int)[:7]}"
    response = client.post(
        "/leads/",
        json={
            "customer_name": "Task Lead",
            "mobile": mobile,
            "source": "site",
            "need": "Needs follow-up",
        },
        headers=headers,
    )

    return response.json()


def test_create_task_for_lead():
    headers = get_admin_headers()
    lead = create_lead(headers)
    due_at = datetime.now(timezone.utc) + timedelta(hours=2)

    response = client.post(
        f"/leads/{lead['id']}/tasks",
        json={
            "title": "Call customer",
            "description": "Ask about budget.",
            "due_at": due_at.isoformat(),
        },
        headers=headers,
    )

    assert response.status_code == 201

    body = response.json()

    assert body["lead_id"] == lead["id"]
    assert body["created_by_id"] == 1
    assert body["assigned_to_id"] == 1
    assert body["title"] == "Call customer"
    assert body["status"] == "pending"


def test_lead_tasks_contains_created_task():
    headers = get_admin_headers()
    lead = create_lead(headers)
    due_at = datetime.now(timezone.utc) + timedelta(hours=3)

    create_response = client.post(
        f"/leads/{lead['id']}/tasks",
        json={
            "title": "Send catalog",
            "description": None,
            "due_at": due_at.isoformat(),
        },
        headers=headers,
    )
    task_id = create_response.json()["id"]

    response = client.get(f"/leads/{lead['id']}/tasks", headers=headers)

    assert response.status_code == 200
    assert any(task["id"] == task_id for task in response.json())


def test_my_tasks_contains_pending_task():
    headers = get_admin_headers()
    lead = create_lead(headers)
    due_at = datetime.now(timezone.utc) + timedelta(hours=4)

    create_response = client.post(
        f"/leads/{lead['id']}/tasks",
        json={
            "title": "Prepare proforma",
            "description": "Customer requested a quote.",
            "due_at": due_at.isoformat(),
        },
        headers=headers,
    )
    task_id = create_response.json()["id"]

    response = client.get("/tasks/my", headers=headers)

    assert response.status_code == 200
    assert any(task["id"] == task_id for task in response.json())


def test_complete_task_updates_status_and_timeline():
    headers = get_admin_headers()
    lead = create_lead(headers)
    due_at = datetime.now(timezone.utc) + timedelta(hours=5)

    create_response = client.post(
        f"/leads/{lead['id']}/tasks",
        json={
            "title": "Follow up",
            "description": "Check customer decision.",
            "due_at": due_at.isoformat(),
        },
        headers=headers,
    )
    task_id = create_response.json()["id"]

    response = client.patch(
        f"/leads/{lead['id']}/tasks/{task_id}/status",
        json={"status": "done"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "done"
    assert response.json()["completed_at"] is not None

    timeline_response = client.get(
        f"/leads/{lead['id']}/activities",
        headers=headers,
    )

    assert any(
        activity["activity_type"] == "task_completed"
        for activity in timeline_response.json()
    )


def test_create_task_requires_authentication():
    due_at = datetime.now(timezone.utc) + timedelta(hours=2)

    response = client.post(
        "/leads/1/tasks",
        json={
            "title": "Unauthorized task",
            "description": None,
            "due_at": due_at.isoformat(),
        },
    )

    assert response.status_code == 401
