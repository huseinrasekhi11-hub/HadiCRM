"""
Integration tests for the canonical success status rename (closed_won -> final_factor).

Prerequisites (same as the rest of the suite):
  * PostgreSQL reachable via DATABASE_URL
  * Admin user exists: mobile 09120000000 / password Admin123!
  * Migrations applied: alembic upgrade head (data rename included)
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


def create_lead(headers, customer_name="Final Factor Customer"):
    response = client.post(
        "/leads/",
        json={
            "customer_name": customer_name,
            "mobile": unique_mobile(),
            "source": "site",
            "need": "final factor rename test",
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def get_product_id(headers, name="پکیج"):
    products = client.get("/products/", headers=headers).json()
    matches = [p for p in products if p["name"] == name]
    assert matches, f"Catalog product '{name}' must exist"
    return matches[0]["id"]


def test_final_factor_status_accepted_and_closes_lead():
    headers = get_admin_headers()
    lead = create_lead(headers)

    response = client.patch(
        f"/leads/{lead['id']}/status",
        json={"status": "final_factor", "sale_amount": 80000000},
        headers=headers,
    )
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "final_factor"
    assert body["sale_amount"] == 80000000
    assert body["is_open"] is False
    assert body["health"] is None


def test_deprecated_closed_won_alias_normalized_to_final_factor():
    headers = get_admin_headers()
    lead = create_lead(headers)

    response = client.patch(
        f"/leads/{lead['id']}/status",
        json={"status": "closed_won", "sale_amount": 15000000},
        headers=headers,
    )
    assert response.status_code == 200

    # مقدار ذخیره‌شده و برگردانده‌شده باید وضعیت رسمی جدید باشد
    assert response.json()["status"] == "final_factor"

    detail = client.get(f"/leads/{lead['id']}", headers=headers)
    assert detail.json()["status"] == "final_factor"


def test_sale_items_allowed_with_final_factor_and_alias():
    headers = get_admin_headers()
    product_id = get_product_id(headers)

    # با مقدار رسمی
    lead_one = create_lead(headers)
    response_one = client.patch(
        f"/leads/{lead_one['id']}/status",
        json={
            "status": "final_factor",
            "sale_items": [{"product_id": product_id, "amount": 35000000}],
        },
        headers=headers,
    )
    assert response_one.status_code == 200
    assert response_one.json()["sale_amount"] == 35000000

    # با نام مستعار منسوخ‌شده
    lead_two = create_lead(headers)
    response_two = client.patch(
        f"/leads/{lead_two['id']}/status",
        json={
            "status": "closed_won",
            "sale_items": [{"product_id": product_id, "amount": 20000000}],
        },
        headers=headers,
    )
    assert response_two.status_code == 200
    assert response_two.json()["status"] == "final_factor"

    items = client.get(f"/leads/{lead_two['id']}/sale-items", headers=headers).json()
    assert len(items) == 1
    assert items[0]["amount"] == 20000000


def test_sale_items_rejected_for_non_won_status():
    headers = get_admin_headers()
    product_id = get_product_id(headers)
    lead = create_lead(headers)

    response = client.patch(
        f"/leads/{lead['id']}/status",
        json={
            "status": "contacted",
            "sale_items": [{"product_id": product_id, "amount": 1000}],
        },
        headers=headers,
    )
    assert response.status_code == 422


def test_closed_lost_still_requires_loss_reason():
    headers = get_admin_headers()
    lead = create_lead(headers)

    without_reason = client.patch(
        f"/leads/{lead['id']}/status",
        json={"status": "closed_lost"},
        headers=headers,
    )
    assert without_reason.status_code == 422

    with_reason = client.patch(
        f"/leads/{lead['id']}/status",
        json={"status": "closed_lost", "loss_reason": "price"},
        headers=headers,
    )
    assert with_reason.status_code == 200
    assert with_reason.json()["status"] == "closed_lost"


def test_search_by_final_factor_and_legacy_alias():
    headers = get_admin_headers()
    lead = create_lead(headers)
    mobile = lead["mobile"]

    client.patch(
        f"/leads/{lead['id']}/status",
        json={"status": "final_factor"},
        headers=headers,
    )

    canonical = client.get(
        "/leads/",
        params={"search": mobile, "status": "final_factor"},
        headers=headers,
    )
    assert any(item["id"] == lead["id"] for item in canonical.json())

    legacy = client.get(
        "/leads/",
        params={"search": mobile, "status": "closed_won"},
        headers=headers,
    )
    assert any(item["id"] == lead["id"] for item in legacy.json())


def test_timeline_records_transition_to_final_factor():
    headers = get_admin_headers()
    lead = create_lead(headers)

    client.patch(
        f"/leads/{lead['id']}/status",
        json={"status": "final_factor"},
        headers=headers,
    )

    timeline = client.get(f"/leads/{lead['id']}/timeline", headers=headers).json()
    matching = [
        activity for activity in timeline
        if activity["activity_type"] == "status_change"
        and "to final_factor" in (activity["description"] or "")
    ]
    assert matching, "Timeline must record the transition into final_factor"


def test_dashboard_counts_final_factor_as_won():
    headers = get_admin_headers()
    lead = create_lead(headers)

    client.patch(
        f"/leads/{lead['id']}/status",
        json={"status": "final_factor", "sale_amount": 42000000},
        headers=headers,
    )

    conversion = client.get("/dashboard/charts/conversion", headers=headers).json()
    assert conversion["won_leads"] >= 1
    assert conversion["total_leads"] == (
        conversion["open_leads"] + conversion["won_leads"] + conversion["lost_leads"]
    )

    daily = client.get(
        "/dashboard/charts/daily-sales",
        params={"days": 7},
        headers=headers,
    ).json()
    assert daily[-1]["amount"] >= 42000000

    admin_row = [
        row for row in client.get("/dashboard/charts/sales-by-user", headers=headers).json()
        if row["user_id"] == 1
    ][0]
    assert admin_row["won_count"] >= 1
    assert admin_row["total_sales"] >= 42000000


def test_top_products_counts_final_factor_sales():
    headers = get_admin_headers()
    product_id = get_product_id(headers, name="رادیاتور")
    lead = create_lead(headers)

    client.patch(
        f"/leads/{lead['id']}/status",
        json={
            "status": "final_factor",
            "sale_items": [{"product_id": product_id, "amount": 60000000}],
        },
        headers=headers,
    )

    top = client.get("/dashboard/charts/top-products", headers=headers).json()
    assert top["total_sales"] >= 60000000

    radiator_row = [
        row for row in top["products"] if row["product_name"] == "رادیاتور"
    ][0]
    assert radiator_row["total_sales"] >= 60000000
    assert radiator_row["lead_count"] >= 1


def test_manager_dashboard_still_works_after_rename():
    headers = get_admin_headers()
    response = client.get("/dashboard/", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert "pipeline" in body
    assert "salesperson_performance" in body
