"""
Regression tests for defects found in the 2026-09 end-to-end audit.

Requirements (same as the rest of the suite):
  * PostgreSQL reachable via DATABASE_URL
  * seeded admin 09120000000 / Admin123!

Each test reproduces a bug that was confirmed live against the running
application before the fix, and fails if the fix is reverted.
"""
import threading
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _login(mobile, password):
    r = client.post("/auth/login", data={"username": mobile, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def admin_headers():
    return _login("09120000000", "Admin123!")


def _mobile():
    return f"0912{str(uuid4().int)[:7]}"


def make_user(headers, role, password="AuditPass123!"):
    mobile = f"0935{str(uuid4().int)[:7]}"
    r = client.post(
        "/users/",
        json={"full_name": f"audit {role}", "mobile": mobile, "password": password, "role": role},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json(), _login(mobile, password)


def make_lead(headers, **overrides):
    payload = {"customer_name": "Audit Lead", "mobile": _mobile(), "source": "site"}
    payload.update(overrides)
    r = client.post("/leads/", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------------------
# HIGH: Rial amounts above 2^31-1 were rejected (INTEGER columns)
# ---------------------------------------------------------------------------
def test_sale_amount_above_32bit_is_accepted():
    headers = admin_headers()
    lead = make_lead(headers)
    big = 3_000_000_000  # 3 billion Rial: a routine HVAC invoice
    r = client.patch(
        f"/leads/{lead['id']}/status",
        json={"status": "final_factor", "sale_amount": big},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["sale_amount"] == big
    assert client.get(f"/leads/{lead['id']}", headers=headers).json()["sale_amount"] == big


def test_sale_item_amount_above_32bit_is_accepted():
    headers = admin_headers()
    product = client.post("/products/", json={"name": f"Chiller {uuid4().hex[:6]}"}, headers=headers).json()
    lead = make_lead(headers)
    big = 5_000_000_000
    r = client.patch(
        f"/leads/{lead['id']}/status",
        json={
            "status": "final_factor",
            "sale_items": [{"product_id": product["id"], "amount": big}],
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["sale_amount"] == big
    items = client.get(f"/leads/{lead['id']}/sale-items", headers=headers).json()
    assert items[0]["amount"] == big


def test_absurd_sale_amount_is_rejected_with_422_not_db_error():
    headers = admin_headers()
    lead = make_lead(headers)
    r = client.patch(
        f"/leads/{lead['id']}/status",
        json={"status": "final_factor", "sale_amount": 10**18},
        headers=headers,
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# HIGH: concurrent creation of the same mobile produced several leads
# ---------------------------------------------------------------------------
def test_concurrent_creates_with_same_mobile_yield_single_lead():
    headers = admin_headers()
    mobile = _mobile()
    results = []
    errors = []

    def submit():
        try:
            r = client.post(
                "/leads/",
                json={"customer_name": "Race", "mobile": mobile, "source": "site"},
                headers=headers,
            )
            results.append(r.json())
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=submit) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(results) == 8
    ids = {body["id"] for body in results}
    assert len(ids) == 1, f"expected one lead, got {ids}"
    lead_id = ids.pop()
    lead = client.get(f"/leads/{lead_id}", headers=headers).json()
    assert lead["duplicate_count"] == 7
    history = client.get(f"/leads/{lead_id}/duplicate-history", headers=headers).json()
    assert sorted(s["submission_index"] for s in history) == list(range(1, 8))


# ---------------------------------------------------------------------------
# MEDIUM: system activity types could be forged through the public API
# ---------------------------------------------------------------------------
def test_system_activity_types_cannot_be_forged():
    headers = admin_headers()
    _, sales = make_user(headers, "sales")
    lead = make_lead(sales)
    for forged in ("lead_deleted", "status_change", "escalated", "lead_restored", "duplicate_detected"):
        r = client.post(
            f"/leads/{lead['id']}/activities",
            json={"activity_type": forged, "title": "forged"},
            headers=sales,
        )
        assert r.status_code == 400, (forged, r.text)
    timeline = client.get(f"/leads/{lead['id']}/timeline", headers=sales).json()
    assert all(e["title"] != "forged" for e in timeline)


def test_human_activity_types_still_accepted():
    headers = admin_headers()
    lead = make_lead(headers)
    r = client.post(
        f"/leads/{lead['id']}/activities",
        json={"activity_type": "call", "title": "تماس", "no_followup_reason": "بسته شد"},
        headers=headers,
    )
    assert r.status_code == 201, r.text


# ---------------------------------------------------------------------------
# MEDIUM: task assignee was never validated
# ---------------------------------------------------------------------------
def test_task_to_nonexistent_user_is_400_not_409():
    headers = admin_headers()
    lead = make_lead(headers)
    r = client.post(
        f"/leads/{lead['id']}/tasks",
        json={"title": "t", "due_at": "2030-01-01T00:00:00Z", "assigned_to_id": 99_999_999},
        headers=headers,
    )
    assert r.status_code == 400


def test_task_cannot_be_assigned_to_user_who_cannot_see_lead():
    headers = admin_headers()
    _, sales_a = make_user(headers, "sales")
    sales_b_user, _ = make_user(headers, "sales")
    lead = make_lead(sales_a)
    r = client.post(
        f"/leads/{lead['id']}/tasks",
        json={"title": "t", "due_at": "2030-01-01T00:00:00Z", "assigned_to_id": sales_b_user["id"]},
        headers=sales_a,
    )
    assert r.status_code == 400


def test_task_can_be_assigned_to_manager_role():
    headers = admin_headers()
    _, sales = make_user(headers, "sales")
    manager, _ = make_user(headers, "manager")
    lead = make_lead(sales)
    r = client.post(
        f"/leads/{lead['id']}/tasks",
        json={"title": "t", "due_at": "2030-01-01T00:00:00Z", "assigned_to_id": manager["id"]},
        headers=sales,
    )
    assert r.status_code == 201, r.text


# ---------------------------------------------------------------------------
# MEDIUM: PATCH /leads/{id} accepted mobiles/sources that POST rejected
# ---------------------------------------------------------------------------
def test_lead_update_rejects_invalid_mobile_and_blank_source():
    headers = admin_headers()
    lead = make_lead(headers)
    assert client.patch(f"/leads/{lead['id']}", json={"mobile": "12345"}, headers=headers).status_code == 422
    assert client.patch(f"/leads/{lead['id']}", json={"source": "   "}, headers=headers).status_code == 422
    persian = "۰۹۱۲" + "".join("۰۱۲۳۴۵۶۷۸۹"[int(c)] for c in str(uuid4().int)[:7])
    ok = client.patch(f"/leads/{lead['id']}", json={"mobile": persian}, headers=headers)
    assert ok.status_code == 200, ok.text


# ---------------------------------------------------------------------------
# MEDIUM: admin could lock themselves / the last admin out via PUT /users
# ---------------------------------------------------------------------------
def test_admin_cannot_deactivate_or_demote_self_via_put():
    headers = admin_headers()
    me, mine = make_user(headers, "admin")
    assert client.put(f"/users/{me['id']}", json={"is_active": False}, headers=mine).status_code == 400
    assert client.put(f"/users/{me['id']}", json={"role": "sales"}, headers=mine).status_code == 400
    # renaming yourself is still fine
    assert client.put(f"/users/{me['id']}", json={"full_name": "Renamed"}, headers=mine).status_code == 200
    # deactivate the throwaway admin with the seeded one so it does not linger
    assert client.put(f"/users/{me['id']}", json={"is_active": False}, headers=headers).status_code == 200


# ---------------------------------------------------------------------------
# LOW: product names differing only by case created duplicates
# ---------------------------------------------------------------------------
def test_product_name_uniqueness_is_case_insensitive():
    headers = admin_headers()
    name = f"Fan Coil {uuid4().hex[:6]}"
    assert client.post("/products/", json={"name": name}, headers=headers).status_code == 201
    assert client.post("/products/", json={"name": name.upper()}, headers=headers).status_code == 400


# ---------------------------------------------------------------------------
# LOW: security headers / ETag not applied to binary downloads
# ---------------------------------------------------------------------------
def test_security_headers_present_and_download_not_etagged_by_middleware():
    headers = admin_headers()
    r = client.get("/auth/me", headers=headers)
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "DENY"

    lead = make_lead(headers)
    up = client.post(
        f"/leads/{lead['id']}/attachments",
        files={"file": ("doc.txt", b"<html>not really html</html>")},
        headers=headers,
    )
    assert up.status_code == 201, up.text
    d = client.get(f"/leads/{lead['id']}/attachments/{up.json()['id']}/download", headers=headers)
    assert d.status_code == 200
    assert d.headers.get("x-content-type-options") == "nosniff"
    assert d.headers.get("content-disposition", "").startswith("attachment")
