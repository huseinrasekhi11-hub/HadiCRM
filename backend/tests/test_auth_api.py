from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_login_returns_access_token_for_admin():
    response = client.post(
        "/auth/login",
        data={
            "username": "09120000000",
            "password": "Admin123!",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_rejects_wrong_password():
    response = client.post(
        "/auth/login",
        data={
            "username": "09120000000",
            "password": "wrong-password",
        },
    )

    assert response.status_code == 401


def test_me_returns_current_user_for_valid_token():
    login_response = client.post(
        "/auth/login",
        data={
            "username": "09120000000",
            "password": "Admin123!",
        },
    )
    token = login_response.json()["access_token"]

    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    # فقط فیلدهای پایدار بررسی می‌شوند تا افزوده‌شدن فیلد جدید به
    # UserResponse این تست را نشکند.
    assert body["id"] == 1
    assert body["full_name"] == "System Administrator"
    assert body["mobile"] == "09120000000"
    assert body["role"] == "admin"
    assert body["is_active"] is True


def test_me_rejects_missing_token():
    response = client.get("/auth/me")

    assert response.status_code == 401


def test_legacy_untyped_jwt_is_rejected():
    import jwt
    from datetime import datetime, timedelta, timezone
    from app.config.settings import settings

    token = jwt.encode(
        {
            "sub": "09120000000",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            "iat": datetime.now(timezone.utc),
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert client.post("/auth/refresh-token", json={"refresh_token": token}).status_code == 401
