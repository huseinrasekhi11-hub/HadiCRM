"""
Integration tests for the silent deletion audit feature.

Prerequisites (same as the rest of the suite):
  * PostgreSQL reachable via DATABASE_URL
  * Admin user exists: mobile 09120000000 / password Admin123!
  * Migrations applied: alembic upgrade head
"""
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


def create_lead(headers, mobile, customer_name="Deletion Test Customer"):
    return client.post(
        "/leads/",
        json={
            "customer_name": customer_name,
            "mobile": mobile,
            "source": "site",
            "need": "Deletion audit check",
        },
        headers=headers,
    )


def create_sales_user(headers):
    """ساخت یک کاربر فروش برای تست رفتار غیرمدیر."""
    mobile = unique_mobile()
    password = "SalesPass123!"
    response = client.post(
        "/users/",
        json={
            "full_name": "Deletion Test Salesperson",
            "mobile": mobile,
            "password": password,
            "role": "sales",
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json(), mobile, password


def test_delete_lead_returns_silent_status():
    headers = get_admin_headers()
    lead = create_lead(headers, unique_mobile()).json()

    response = client.delete(f"/leads/{lead['id']}", headers=headers)
    assert response.status_code == 200

    body = response.json()
    # پاسخ باید دقیقاً یک حذف موفق معمولی باشد؛ هیچ کلیدی مربوط به
    # ممیزی/لاگ/اسنپ‌شات نباید وجود داشته باشد
    assert body == {"status": "deleted"}


def test_deleted_lead_disappears_from_user_views():
    headers = get_admin_headers()
    mobile = unique_mobile()
    lead = create_lead(headers, mobile).json()

    client.delete(f"/leads/{lead['id']}", headers=headers)

    detail = client.get(f"/leads/{lead['id']}", headers=headers)
    assert detail.status_code == 404

    my_leads = client.get("/leads/my", headers=headers).json()
    assert all(item["mobile"] != mobile for item in my_leads)


def test_deleted_leads_endpoint_requires_admin_role():
    admin_headers = get_admin_headers()
    sales_user, mobile, password = create_sales_user(admin_headers)
    sales_headers = login(mobile, password)

    # بدون توکن
    assert client.get("/deleted-leads/").status_code == 401
    # کاربر فروش -> 403
    assert client.get("/deleted-leads/", headers=sales_headers).status_code == 403
    # ادمین -> 200
    assert client.get("/deleted-leads/", headers=admin_headers).status_code == 200


def test_admin_sees_deleted_lead_with_full_audit_fields():
    admin_headers = get_admin_headers()
    mobile = unique_mobile()
    lead = create_lead(admin_headers, mobile, customer_name="Audit Snapshot Customer").json()

    delete_response = client.delete(f"/leads/{lead['id']}", headers=admin_headers)
    assert delete_response.status_code == 200

    response = client.get(
        "/deleted-leads/",
        params={"search": mobile},
        headers=admin_headers,
    )
    assert response.status_code == 200

    records = [item for item in response.json() if item["lead_id"] == lead["id"]]
    assert len(records) == 1

    record = records[0]
    assert record["customer_name"] == "Audit Snapshot Customer"
    assert record["mobile"] == mobile
    assert record["mobile_normalized"] == mobile
    assert record["previous_status"] == "new"
    assert record["owner_id"] == lead["owner_id"]
    assert record["owner_full_name"] == "System Administrator"
    assert record["deleted_by_id"] == 1
    assert record["deleted_by_full_name"] == "System Administrator"
    assert record["deleted_at"]
    assert record["restored_at"] is None


def test_deleted_lead_detail_contains_full_snapshot():
    admin_headers = get_admin_headers()
    lead = create_lead(admin_headers, unique_mobile()).json()
    client.delete(f"/leads/{lead['id']}", headers=admin_headers)

    listing = client.get(
        "/deleted-leads/",
        params={"search": lead["mobile"]},
        headers=admin_headers,
    ).json()
    audit_id = [item for item in listing if item["lead_id"] == lead["id"]][0]["id"]

    detail = client.get(f"/deleted-leads/{audit_id}", headers=admin_headers)
    assert detail.status_code == 200

    body = detail.json()
    assert body["snapshot"]["id"] == lead["id"]
    assert body["snapshot"]["customer_name"] == lead["customer_name"]
    assert body["snapshot"]["status"] == "new"
    assert body["snapshot"]["owner_id"] == lead["owner_id"]
    assert body["snapshot"]["source"] == "site"


def test_deleted_leads_filters_by_deleter_and_date():
    admin_headers = get_admin_headers()
    sales_user, mobile, password = create_sales_user(admin_headers)
    sales_headers = login(mobile, password)

    lead = create_lead(sales_headers, unique_mobile()).json()
    client.delete(f"/leads/{lead['id']}", headers=sales_headers)

    # فیلتر بر اساس حذف‌کننده
    by_deleter = client.get(
        "/deleted-leads/",
        params={"deleted_by_id": sales_user["id"]},
        headers=admin_headers,
    ).json()
    assert any(item["lead_id"] == lead["id"] for item in by_deleter)
    assert all(item["deleted_by_id"] == sales_user["id"] for item in by_deleter)

    # فیلتر بازه‌ی زمانی: گذشته‌ی دور باید خالی از این رکورد باشد
    old_window = client.get(
        "/deleted-leads/",
        params={
            "deleted_by_id": sales_user["id"],
            "date_from": "2020-01-01T00:00:00Z",
            "date_to": "2020-01-02T00:00:00Z",
        },
        headers=admin_headers,
    ).json()
    assert all(item["lead_id"] != lead["id"] for item in old_window)


def test_salesperson_can_delete_own_lead_and_admin_sees_deleter():
    admin_headers = get_admin_headers()
    sales_user, mobile, password = create_sales_user(admin_headers)
    sales_headers = login(mobile, password)

    lead = create_lead(sales_headers, unique_mobile()).json()

    delete_response = client.delete(f"/leads/{lead['id']}", headers=sales_headers)
    assert delete_response.status_code == 200
    assert delete_response.json() == {"status": "deleted"}

    records = client.get(
        "/deleted-leads/",
        params={"deleted_by_id": sales_user["id"]},
        headers=admin_headers,
    ).json()
    record = [item for item in records if item["lead_id"] == lead["id"]][0]
    assert record["deleted_by_full_name"] == "Deletion Test Salesperson"
    assert record["owner_id"] == sales_user["id"]


def test_restore_lead_makes_it_visible_again():
    admin_headers = get_admin_headers()
    mobile = unique_mobile()
    lead = create_lead(admin_headers, mobile).json()
    client.delete(f"/leads/{lead['id']}", headers=admin_headers)

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
    body = restore_response.json()
    assert body["status"] == "restored"
    assert body["lead_id"] == lead["id"]
    assert body["restored_at"]

    # پرونده دوباره در دسترس است
    detail = client.get(f"/leads/{lead['id']}", headers=admin_headers)
    assert detail.status_code == 200
    assert detail.json()["mobile"] == mobile

    # رکورد ممیزی، وضعیت احیا را نشان می‌دهد
    records = client.get(
        "/deleted-leads/",
        params={"search": mobile},
        headers=admin_headers,
    ).json()
    assert records[0]["restored_at"] is not None

    # احیای دوباره -> خطا
    second_restore = client.post(
        f"/deleted-leads/{audit_id}/restore",
        headers=admin_headers,
    )
    assert second_restore.status_code == 400


def test_deleted_lead_can_still_be_found_after_restore_via_search():
    admin_headers = get_admin_headers()
    mobile = unique_mobile()
    lead = create_lead(admin_headers, mobile).json()
    client.delete(f"/leads/{lead['id']}", headers=admin_headers)

    listing = client.get(
        "/deleted-leads/",
        params={"search": mobile},
        headers=admin_headers,
    ).json()
    audit_id = [item for item in listing if item["lead_id"] == lead["id"]][0]["id"]
    client.post(f"/deleted-leads/{audit_id}/restore", headers=admin_headers)

    search = client.get("/leads/", params={"search": mobile}, headers=admin_headers)
    assert any(item["id"] == lead["id"] for item in search.json())


def test_restore_rejects_when_mobile_is_now_used_by_another_active_lead():
    admin_headers = get_admin_headers()
    mobile = unique_mobile()

    original = create_lead(admin_headers, mobile, "Original Customer").json()
    assert client.delete(f"/leads/{original['id']}", headers=admin_headers).status_code == 200

    replacement = create_lead(admin_headers, mobile, "Replacement Customer")
    assert replacement.status_code == 201

    listing = client.get(
        "/deleted-leads/",
        params={"search": mobile, "include_restored": False},
        headers=admin_headers,
    ).json()
    audit_id = next(item["id"] for item in listing if item["lead_id"] == original["id"])

    response = client.post(f"/deleted-leads/{audit_id}/restore", headers=admin_headers)
    assert response.status_code == 409
    assert client.get(f"/deleted-leads/{audit_id}", headers=admin_headers).json()["restored_at"] is None
    assert client.get(f"/leads/{original['id']}", headers=admin_headers).status_code == 404
