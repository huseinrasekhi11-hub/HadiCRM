from uuid import uuid4

from fastapi.testclient import TestClient

from app.database.database import SessionLocal
from app.crud.notification import create_notification
from app.main import app

client = TestClient(app)


def mobile():
    return f"0912{str(uuid4().int)[:7]}"


def login(m, p):
    res = client.post("/auth/login", data={"username": m, "password": p})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_deleted_lead_notifications_are_hidden_from_ordinary_users():
    admin = login("09120000000", "Admin123!")
    user_mobile = mobile()

    created = client.post(
        "/users/",
        headers=admin,
        json={
            "full_name": "Notification Visibility User",
            "mobile": user_mobile,
            "password": "StrongPass!123",
            "role": "sales",
        },
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]
    user = login(user_mobile, "StrongPass!123")

    lead_res = client.post(
        "/leads/",
        headers=user,
        json={
            "customer_name": "Deleted Notification Customer",
            "mobile": mobile(),
            "source": "site",
            "need": None,
        },
    )
    assert lead_res.status_code == 201, lead_res.text
    lead_id = lead_res.json()["id"]

    db = SessionLocal()
    try:
        create_notification(
            db,
            user_id=user_id,
            notification_type="lead_assigned",
            title="Historical lead notification",
            message="Deleted Notification Customer was assigned to you.",
            lead_id=lead_id,
        )
    finally:
        db.close()

    before = client.get("/notifications/feed", headers=user)
    assert before.status_code == 200, before.text
    assert any(item["lead_id"] == lead_id for item in before.json())

    deleted = client.delete(f"/leads/{lead_id}", headers=user)
    assert deleted.status_code == 200, deleted.text

    after = client.get("/notifications/feed", headers=user)
    assert after.status_code == 200, after.text
    assert all(item["lead_id"] != lead_id for item in after.json())
