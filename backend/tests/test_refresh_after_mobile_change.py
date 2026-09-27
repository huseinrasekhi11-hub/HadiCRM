from uuid import uuid4

from fastapi.testclient import TestClient

from app.config.settings import settings
from app.main import app

client = TestClient(app, base_url="https://testserver")
COOKIE_NAME = settings.REFRESH_COOKIE_NAME


def unique_mobile(prefix="0918"):
    return f"{prefix}{str(uuid4().int)[:7]}"


def login(mobile, password):
    return client.post("/auth/login", data={"username": mobile, "password": password})


def admin_headers():
    res = login("09120000000", "Admin123!")
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_refresh_survives_mobile_number_change():
    admin = admin_headers()
    old_mobile = unique_mobile()
    new_mobile = unique_mobile()

    created = client.post(
        "/users/",
        headers=admin,
        json={
            "full_name": "Refresh Identity Change",
            "mobile": old_mobile,
            "password": "StrongPass!123",
            "role": "sales",
        },
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]

    client.cookies.clear()
    logged_in = login(old_mobile, "StrongPass!123")
    assert logged_in.status_code == 200
    refresh_cookie = client.cookies.get(COOKIE_NAME)
    assert refresh_cookie

    changed = client.put(
        f"/users/{user_id}",
        headers=admin,
        json={"mobile": new_mobile},
    )
    assert changed.status_code == 200, changed.text

    refreshed = client.post("/auth/refresh-token", json={})
    assert refreshed.status_code == 200, refreshed.text
    assert "refresh_token" not in refreshed.json()
