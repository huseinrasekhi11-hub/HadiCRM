"""
Full-stack QA regression tests (Part 15).
Covers: CORS exposure, ETag/conditional requests, pagination params,
status alias behavior, and core permission boundaries.

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


def create_lead(headers, mobile=None):
    return client.post(
        "/leads/",
        json={
            "customer_name": "QA Customer",
            "mobile": mobile or unique_mobile(),
            "source": "site",
            "need": None,
        },
        headers=headers,
    )


# ---------- CORS / pagination header exposure ----------
def test_cors_exposes_pagination_header():
    headers = get_admin_headers()
    # CORSMiddleware only decorates responses to actual cross-origin
    # requests; a browser always sends Origin, so the test must too.
    headers["Origin"] = "http://localhost:5173"
    response = client.get("/leads/?limit=1", headers=headers)
    assert response.status_code == 200
    # expose_headers must make X-Total-Count readable by the browser
    exposed = response.headers.get("access-control-expose-headers", "")
    assert "X-Total-Count" in exposed


# ---------- ETag / conditional requests ----------
def test_etag_present_and_conditional_304():
    headers = get_admin_headers()
    create_lead(headers)

    first = client.get("/leads/?limit=5", headers=headers)
    assert first.status_code == 200
    etag = first.headers.get("etag")
    assert etag, "ETag middleware must tag GET responses"

    second = client.get(
        "/leads/?limit=5", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == 304


# ---------- Pagination params ----------
def test_pagination_params_accepted():
    headers = get_admin_headers()
    for _ in range(3):
        create_lead(headers)
    page = client.get("/leads/?skip=0&limit=2", headers=headers)
    assert page.status_code == 200
    assert len(page.json()) <= 2


# ---------- Status handling ----------
def test_status_filter_and_closed_lost_requires_reason():
    headers = get_admin_headers()
    lead = create_lead(headers).json()

    # Filter by open status works
    filtered = client.get("/leads/?status=new", headers=headers)
    assert filtered.status_code == 200

    # closed_lost without reason -> 422
    bad = client.patch(
        f"/leads/{lead['id']}/status",
        json={"status": "closed_lost"},
        headers=headers,
    )
    assert bad.status_code == 422

    # closed_lost with reason -> 200
    good = client.patch(
        f"/leads/{lead['id']}/status",
        json={"status": "closed_lost", "loss_reason": "price"},
        headers=headers,
    )
    assert good.status_code == 200
    assert good.json()["status"] == "closed_lost"


# ---------- Permission boundaries ----------
def test_sales_isolation_and_admin_surfaces():
    admin_headers = get_admin_headers()

    # create a sales user
    mobile = unique_mobile()
    client.post(
        "/users/",
        json={
            "full_name": "QA Sales",
            "mobile": mobile,
            "password": "QAPass123!",
            "role": "sales",
        },
        headers=admin_headers,
    )
    sales_headers = login(mobile, "QAPass123!")

    lead = create_lead(admin_headers).json()

    # sales cannot see admin's lead
    assert client.get(f"/leads/{lead['id']}", headers=sales_headers).status_code == 404

    # sales blocked from admin-only surfaces
    for endpoint in ("/deleted-leads/", "/dashboard/charts/conversion"):
        assert client.get(endpoint, headers=sales_headers).status_code == 403

    # admin can access
    assert client.get("/deleted-leads/", headers=admin_headers).status_code == 200


# ---------- Dashboard sanity ----------
def test_dashboard_returns_200_for_admin_and_sales():
    admin_headers = get_admin_headers()
    assert client.get("/dashboard/", headers=admin_headers).status_code == 200

    mobile = unique_mobile()
    client.post(
        "/users/",
        json={
            "full_name": "QA Dashboard Sales",
            "mobile": mobile,
            "password": "QAPass123!",
            "role": "sales",
        },
        headers=admin_headers,
    )
    sales_headers = login(mobile, "QAPass123!")
    assert client.get("/dashboard/", headers=sales_headers).status_code == 200
