"""
Integration tests for Part 4: pipeline counts endpoint, lead update,
and paginated search totals.
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


def create_user(headers, full_name: str, role: str):
    mobile = unique_mobile()
    password = "PipelineTest123!"
    response = client.post(
        "/users/",
        json={"full_name": full_name, "mobile": mobile, "password": password, "role": role},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json(), login(mobile, password)


def create_lead(headers, mobile=None, customer_name="Pipeline Customer"):
    response = client.post(
        "/leads/",
        json={
            "customer_name": customer_name,
            "mobile": mobile or unique_mobile(),
            "source": "site",
            "need": None,
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


PIPELINE_ORDER = [
    "new", "contacted", "no_answer", "negotiating", "waiting_customer",
    "catalog_sent", "price_sent", "proforma", "invoice", "final_factor", "closed_lost",
]


def test_pipeline_counts_zero_filled_and_ordered():
    headers = get_admin_headers()
    create_lead(headers)
    response = client.get("/leads/pipeline", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert "total" in body
    assert [stage["status"] for stage in body["stages"]] == PIPELINE_ORDER
    assert body["total"] == sum(stage["count"] for stage in body["stages"])
    new_stage = [s for s in body["stages"] if s["status"] == "new"][0]
    assert new_stage["count"] >= 1


def test_pipeline_counts_scoped_for_sales():
    admin_headers = get_admin_headers()
    _, sales_headers = create_user(admin_headers, "Pipeline Scope Sales", "sales")
    create_lead(sales_headers)
    body = client.get("/leads/pipeline", headers=sales_headers).json()
    # جمع پایپ‌لاین کارشناس باید دقیقاً با لیست پرونده‌هایش برابر باشد
    my_leads = client.get("/leads/my", headers=sales_headers).json()
    assert body["total"] == len(my_leads)


def test_pipeline_counts_respect_search():
    headers = get_admin_headers()
    mobile = unique_mobile()
    create_lead(headers, mobile=mobile, customer_name="Pipeline Search Target")
    body = client.get("/leads/pipeline", params={"search": mobile}, headers=headers).json()
    assert body["total"] == 1
    assert body["stages"][0]["status"] == "new"
    assert body["stages"][0]["count"] == 1


def test_pipeline_requires_authentication():
    assert client.get("/leads/pipeline").status_code == 401


def test_search_with_total_header():
    headers = get_admin_headers()
    create_lead(headers)
    response = client.get("/leads/", params={"with_total": "true", "limit": 5}, headers=headers)
    assert response.status_code == 200
    total = int(response.headers["x-total-count"])
    assert total >= len(response.json()) >= 1
    # بدون پارامتر، هدر نباید حاضر باشد
    plain = client.get("/leads/", headers=headers)
    assert "x-total-count" not in plain.headers


def test_update_lead_fields_and_renormalize():
    headers = get_admin_headers()
    lead = create_lead(headers)
    new_mobile = f"+98 {unique_mobile()[1:]}"
    response = client.patch(
        f"/leads/{lead['id']}",
        json={"customer_name": "ویرایش شده", "mobile": new_mobile, "need": "نیاز جدید"},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["customer_name"] == "ویرایش شده"
    assert body["mobile"] == new_mobile
    assert body["mobile_normalized"] == new_mobile.replace("+98 ", "0")
    assert body["need"] == "نیاز جدید"


def test_update_lead_mobile_collision_rejected():
    headers = get_admin_headers()
    lead_a = create_lead(headers)
    lead_b = create_lead(headers)
    response = client.patch(
        f"/leads/{lead_a['id']}",
        json={"mobile": lead_b["mobile"]},
        headers=headers,
    )
    assert response.status_code == 400


def test_update_lead_invalid_mobile_rejected():
    headers = get_admin_headers()
    lead = create_lead(headers)
    response = client.patch(f"/leads/{lead['id']}", json={"mobile": "abc"}, headers=headers)
    # Mobile format is now validated at the schema boundary (same rule and
    # status as POST /leads/), so this is a 422 rather than the old 400
    # raised from the CRUD layer.
    assert response.status_code == 422


def test_update_lead_empty_payload_rejected():
    headers = get_admin_headers()
    lead = create_lead(headers)
    response = client.patch(f"/leads/{lead['id']}", json={}, headers=headers)
    assert response.status_code == 422


def test_update_lead_blank_name_rejected():
    headers = get_admin_headers()
    lead = create_lead(headers)
    response = client.patch(
        f"/leads/{lead['id']}", json={"customer_name": "   "}, headers=headers
    )
    assert response.status_code == 422


def test_sales_cannot_update_foreign_lead():
    admin_headers = get_admin_headers()
    _, sales_a_headers = create_user(admin_headers, "Pipeline Update A", "sales")
    _, sales_b_headers = create_user(admin_headers, "Pipeline Update B", "sales")
    lead = create_lead(sales_a_headers)
    response = client.patch(
        f"/leads/{lead['id']}",
        json={"customer_name": "تلاش غیرمجاز"},
        headers=sales_b_headers,
    )
    assert response.status_code == 404


def test_manager_can_update_any_lead():
    admin_headers = get_admin_headers()
    _, sales_headers = create_user(admin_headers, "Pipeline Mgr Target", "sales")
    manager, manager_headers = create_user(admin_headers, "Pipeline Manager", "manager")
    lead = create_lead(sales_headers)
    response = client.patch(
        f"/leads/{lead['id']}",
        json={"source": "manager-edit"},
        headers=manager_headers,
    )
    assert response.status_code == 200
    assert response.json()["source"] == "manager-edit"
