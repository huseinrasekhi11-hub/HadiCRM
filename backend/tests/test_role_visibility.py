"""
Integration tests for role-based lead visibility hardening.

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
    password = "RoleTest123!"
    response = client.post(
        "/users/",
        json={
            "full_name": full_name,
            "mobile": mobile,
            "password": password,
            "role": role,
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json(), login(mobile, password)


def create_lead(headers, customer_name="Role Visibility Customer"):
    response = client.post(
        "/leads/",
        json={
            "customer_name": customer_name,
            "mobile": unique_mobile(),
            "source": "site",
            "need": None,
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


# ---------------------------------------------------------------
# ایزولاسیون کارشناسان فروش
# ---------------------------------------------------------------
def test_sales_user_sees_only_own_leads():
    admin_headers = get_admin_headers()
    sales_a, headers_a = create_user(admin_headers, "Visibility Sales A", "sales")
    sales_b, headers_b = create_user(admin_headers, "Visibility Sales B", "sales")

    leads_a = [create_lead(headers_a, f"A Customer {i}") for i in range(3)]
    leads_b = [create_lead(headers_b, f"B Customer {i}") for i in range(2)]

    # لیست «پرونده‌های من» فقط شامل پرونده‌های خود کاربر
    my_a = client.get("/leads/my", headers=headers_a).json()
    assert len(my_a) == 3
    assert all(item["owner_id"] == sales_a["id"] for item in my_a)

    # جستجو هم نباید نشت کند
    search_a = client.get("/leads/", headers=headers_a).json()
    assert all(item["owner_id"] == sales_a["id"] for item in search_a)

    # جزئیات و تایم‌لاین پرونده‌های کاربر دیگر -> 404
    for lead_b in leads_b:
        assert client.get(f"/leads/{lead_b['id']}", headers=headers_a).status_code == 404
        assert (
            client.get(f"/leads/{lead_b['id']}/timeline", headers=headers_a).status_code
            == 404
        )

    # جستجو با موبایل پرونده‌ی کاربر دیگر -> نتیجه‌ای نیست
    for lead_a in leads_a:
        leaked = client.get(
            "/leads/",
            params={"search": lead_a["mobile"]},
            headers=headers_b,
        ).json()
        assert all(item["owner_id"] != sales_a["id"] for item in leaked)


def test_admin_sees_all_leads():
    admin_headers = get_admin_headers()
    sales_a, headers_a = create_user(admin_headers, "Visibility Admin Check", "sales")
    lead = create_lead(headers_a)

    admin_list = client.get("/leads/my", headers=admin_headers).json()
    assert any(item["id"] == lead["id"] for item in admin_list)

    detail = client.get(f"/leads/{lead['id']}", headers=admin_headers)
    assert detail.status_code == 200


# ---------------------------------------------------------------
# دامنه‌ی نظارتی مدیر و مدیر فروش
# ---------------------------------------------------------------
def test_manager_sees_all_leads_and_subresources():
    admin_headers = get_admin_headers()
    sales_a, headers_a = create_user(admin_headers, "Visibility Mgr Sales", "sales")
    manager, headers_m = create_user(admin_headers, "Visibility Manager", "manager")

    lead = create_lead(headers_a)

    my_m = client.get("/leads/my", headers=headers_m).json()
    assert any(item["id"] == lead["id"] for item in my_m)

    detail = client.get(f"/leads/{lead['id']}", headers=headers_m)
    assert detail.status_code == 200

    for sub in ("timeline", "duplicate-history", "assignments", "escalations", "related-leads"):
        assert (
            client.get(f"/leads/{lead['id']}/{sub}", headers=headers_m).status_code == 200
        ), sub


def test_sales_manager_has_full_scope_and_manager_dashboard():
    admin_headers = get_admin_headers()
    sales_a, headers_a = create_user(admin_headers, "Visibility SM Sales", "sales")
    sales_manager, headers_sm = create_user(
        admin_headers, "Visibility Sales Manager", "sales_manager"
    )

    lead = create_lead(headers_a)

    assert (
        client.get(f"/leads/{lead['id']}", headers=headers_sm).status_code == 200
    )

    dashboard = client.get("/dashboard/", headers=headers_sm)
    assert dashboard.status_code == 200
    body = dashboard.json()
    assert "pipeline" in body
    assert "salesperson_performance" in body


def test_service_manager_keeps_owner_only_scope():
    admin_headers = get_admin_headers()
    sales_a, headers_a = create_user(admin_headers, "Visibility Svc Sales", "sales")
    service_manager, headers_svc = create_user(
        admin_headers, "Visibility Service Manager", "service_manager"
    )

    lead = create_lead(headers_a)

    # مدیر خدمات دامنه‌ی فروش ندارد: پرونده‌ی دیگران را نمی‌بیند
    assert (
        client.get(f"/leads/{lead['id']}", headers=headers_svc).status_code == 404
    )

    own_lead = create_lead(headers_svc)
    my_svc = client.get("/leads/my", headers=headers_svc).json()
    assert all(item["owner_id"] == service_manager["id"] for item in my_svc)
    assert any(item["id"] == own_lead["id"] for item in my_svc)


# ---------------------------------------------------------------
# ارجاع
# ---------------------------------------------------------------
def test_manager_can_assign_any_lead():
    admin_headers = get_admin_headers()
    sales_a, headers_a = create_user(admin_headers, "Visibility Assign A", "sales")
    sales_b, headers_b = create_user(admin_headers, "Visibility Assign B", "sales")
    manager, headers_m = create_user(admin_headers, "Visibility Assign Mgr", "manager")

    lead = create_lead(headers_a)

    response = client.patch(
        f"/leads/{lead['id']}/assign",
        json={"owner_id": sales_b["id"], "note": "manager reassignment"},
        headers=headers_m,
    )
    assert response.status_code == 200
    assert response.json()["owner_id"] == sales_b["id"]


def test_owner_sales_can_assign_own_lead():
    admin_headers = get_admin_headers()
    sales_a, headers_a = create_user(admin_headers, "Visibility Own Assign A", "sales")
    sales_b, headers_b = create_user(admin_headers, "Visibility Own Assign B", "sales")

    lead = create_lead(headers_a)

    response = client.patch(
        f"/leads/{lead['id']}/assign",
        json={"owner_id": sales_b["id"]},
        headers=headers_a,
    )
    assert response.status_code == 200
    assert response.json()["owner_id"] == sales_b["id"]


def test_sales_cannot_assign_others_lead():
    admin_headers = get_admin_headers()
    sales_a, headers_a = create_user(admin_headers, "Visibility NoAssign A", "sales")
    sales_b, headers_b = create_user(admin_headers, "Visibility NoAssign B", "sales")

    lead = create_lead(headers_a)

    response = client.patch(
        f"/leads/{lead['id']}/assign",
        json={"owner_id": sales_b["id"]},
        headers=headers_b,
    )
    # Lead is invisible to sales_b (owner-scoped visibility) -> 404, matching
    # the anti-leak convention asserted by the delete/related-leads tests.
    assert response.status_code == 404


# ---------------------------------------------------------------
# حذف توسط مدیر + ممیزی نامحسوس
# ---------------------------------------------------------------
def test_manager_delete_is_silent_and_audited_for_admin():
    admin_headers = get_admin_headers()
    sales_a, headers_a = create_user(admin_headers, "Visibility Del Sales", "sales")
    manager, headers_m = create_user(admin_headers, "Visibility Del Manager", "manager")

    lead = create_lead(headers_a)

    delete_response = client.delete(f"/leads/{lead['id']}", headers=headers_m)
    assert delete_response.status_code == 200
    # پاسخ کاملاً خنثی — هیچ اشاره‌ای به ممیزی وجود ندارد
    assert delete_response.json() == {"status": "deleted"}

    # مدیر ممیزی حذف را می‌بیند
    audits = client.get(
        "/deleted-leads/",
        params={"deleted_by_id": manager["id"]},
        headers=admin_headers,
    ).json()
    matching = [item for item in audits if item["lead_id"] == lead["id"]]
    assert matching
    assert matching[0]["deleted_by_full_name"] == "Visibility Del Manager"
    assert matching[0]["owner_id"] == sales_a["id"]


def test_sales_cannot_delete_others_lead():
    admin_headers = get_admin_headers()
    sales_a, headers_a = create_user(admin_headers, "Visibility NoDel A", "sales")
    sales_b, headers_b = create_user(admin_headers, "Visibility NoDel B", "sales")

    lead = create_lead(headers_a)

    assert client.delete(f"/leads/{lead['id']}", headers=headers_b).status_code == 404


# ---------------------------------------------------------------
# سطح ممیزی فقط برای ادمین/مدیرعامل باقی می‌ماند
# ---------------------------------------------------------------
def test_manager_blocked_from_admin_only_surfaces():
    admin_headers = get_admin_headers()
    manager, headers_m = create_user(admin_headers, "Visibility Blocked Mgr", "manager")
    sales_user, headers_s = create_user(admin_headers, "Visibility Blocked Sales", "sales")

    lead = create_lead(headers_s)

    for headers in (headers_m, headers_s):
        assert client.get("/deleted-leads/", headers=headers).status_code == 403
        assert (
            client.get(f"/admin/leads/{lead['id']}/timeline", headers=headers).status_code
            == 403
        )
        assert (
            client.get("/dashboard/charts/conversion", headers=headers).status_code == 403
        )
        assert client.get("/audit-logs/", headers=headers).status_code == 403
        assert client.get("/users/", headers=headers).status_code == 403


def test_related_leads_not_leaked_to_other_sales():
    admin_headers = get_admin_headers()
    sales_a, headers_a = create_user(admin_headers, "Visibility Related A", "sales")
    sales_b, headers_b = create_user(admin_headers, "Visibility Related B", "sales")
    manager, headers_m = create_user(admin_headers, "Visibility Related Mgr", "manager")

    lead = create_lead(headers_a)

    # کاربر دیگر اصلاً به خود پرونده دسترسی ندارد -> 404
    assert (
        client.get(f"/leads/{lead['id']}/related-leads", headers=headers_b).status_code
        == 404
    )

    # مدیر به پرونده و پرونده‌های مرتبط دسترسی دارد
    assert (
        client.get(f"/leads/{lead['id']}/related-leads", headers=headers_m).status_code
        == 200
    )
