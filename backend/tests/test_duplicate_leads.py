"""
Integration tests for the repeated-lead integration feature.

Prerequisites (same as the rest of the suite):
  * PostgreSQL reachable via DATABASE_URL
  * Admin user exists: mobile 09120000000 / password Admin123!
  * Migration applied: alembic upgrade head
"""
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

_PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def get_admin_headers():
    response = client.post(
        "/auth/login",
        data={
            "username": "09120000000",
            "password": "Admin123!",
        },
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def unique_mobile():
    return f"0912{str(uuid4().int)[:7]}"


def create_lead(headers, mobile, customer_name="Duplicate Test Customer", source="site"):
    return client.post(
        "/leads/",
        json={
            "customer_name": customer_name,
            "mobile": mobile,
            "source": source,
            "need": "Duplicate integration check",
        },
        headers=headers,
    )


def test_create_lead_stores_normalized_mobile():
    headers = get_admin_headers()
    mobile = unique_mobile()

    response = create_lead(headers, mobile)
    assert response.status_code == 201

    body = response.json()
    assert body["mobile"] == mobile
    assert body["mobile_normalized"] == mobile
    assert body["duplicate_count"] == 0


def test_exact_duplicate_returns_existing_lead_and_increments_counter():
    headers = get_admin_headers()
    mobile = unique_mobile()

    first = create_lead(headers, mobile)
    assert first.status_code == 201
    first_body = first.json()

    second = create_lead(headers, mobile, customer_name="Duplicate Test Customer")
    assert second.status_code == 201
    second_body = second.json()

    # Same canonical lead is returned — no isolated duplicate was created
    assert second_body["id"] == first_body["id"]
    assert second_body["duplicate_count"] == 1

    third = create_lead(headers, mobile)
    assert third.json()["id"] == first_body["id"]
    assert third.json()["duplicate_count"] == 2


def test_mobile_format_variants_resolve_to_same_lead():
    headers = get_admin_headers()
    mobile = unique_mobile()  # 0912XXXXXXX
    last_ten = mobile[1:]     # 912XXXXXXX without leading zero

    first = create_lead(headers, mobile)
    first_id = first.json()["id"]

    variants = [
        f"+98 {last_ten}",              # +98 with spaces
        f"0098{last_ten}",              # 0098 prefix
        f"98-{last_ten}",               # 98 prefix with separator
        mobile.translate(_PERSIAN_DIGITS),  # full Persian digits
        f"۰۹۱۲ {last_ten[3:]}" if False else mobile[:4] + " " + mobile[4:],  # spacing
    ]

    for variant in variants:
        response = create_lead(headers, variant)
        assert response.status_code == 201, f"Variant failed: {variant}"
        assert response.json()["id"] == first_id, f"Variant not merged: {variant}"

    final = client.get(f"/leads/{first_id}", headers=headers)
    assert final.json()["duplicate_count"] == len(variants)


def test_different_mobile_creates_new_lead():
    headers = get_admin_headers()

    first = create_lead(headers, unique_mobile())
    second = create_lead(headers, unique_mobile())

    assert first.json()["id"] != second.json()["id"]
    assert second.json()["duplicate_count"] == 0


def test_duplicate_does_not_create_isolated_lead():
    headers = get_admin_headers()
    mobile = unique_mobile()

    lead = create_lead(headers, mobile).json()
    create_lead(headers, mobile)

    response = client.get("/leads/my", headers=headers)
    assert response.status_code == 200

    matches = [
        item for item in response.json()
        if item["mobile_normalized"] == mobile
    ]
    assert len(matches) == 1
    assert matches[0]["id"] == lead["id"]
    assert matches[0]["duplicate_count"] == 1


def test_duplicate_history_lists_submissions_with_submitter():
    headers = get_admin_headers()
    mobile = unique_mobile()

    lead = create_lead(headers, mobile).json()
    create_lead(headers, mobile, source="instagram")
    create_lead(headers, f"+98{mobile[1:]}", source="referral")

    response = client.get(f"/leads/{lead['id']}/duplicate-history", headers=headers)
    assert response.status_code == 200

    submissions = response.json()
    assert len(submissions) == 2

    # Newest first
    assert submissions[0]["submission_index"] == 2
    assert submissions[1]["submission_index"] == 1

    for submission in submissions:
        assert submission["lead_id"] == lead["id"]
        assert submission["submitted_by_id"] == 1
        assert submission["submitted_by_full_name"] == "System Administrator"
        assert submission["mobile_normalized"] == mobile
        assert submission["matched_by"] in ("mobile", "mobile_and_name")
        assert submission["submitted_at"]


def test_duplicate_history_requires_authentication():
    response = client.get("/leads/1/duplicate-history")
    assert response.status_code == 401


def test_timeline_contains_duplicate_detected_activity():
    headers = get_admin_headers()
    mobile = unique_mobile()

    lead = create_lead(headers, mobile).json()
    create_lead(headers, mobile)

    response = client.get(f"/leads/{lead['id']}/timeline", headers=headers)
    assert response.status_code == 200

    activity_types = [activity["activity_type"] for activity in response.json()]
    assert "lead_created" in activity_types
    assert "duplicate_detected" in activity_types


def test_related_leads_empty_for_unique_mobile():
    headers = get_admin_headers()

    lead = create_lead(headers, unique_mobile()).json()

    response = client.get(f"/leads/{lead['id']}/related-leads", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


def _create_sales_user_and_login():
    """
    A genuinely separate, non-privileged (role='sales') account — distinct
    from the admin used everywhere else in this file. The cross-user
    duplicate-lead leak below is invisible to any test that only ever
    uses the admin account on both sides of a "duplicate", since admin
    can legitimately see any lead.
    """
    admin_headers = get_admin_headers()
    mobile = unique_mobile()
    password = "SalesTest123!"
    response = client.post(
        "/users/",
        json={
            "full_name": "Duplicate Leak Regression Rep",
            "mobile": mobile,
            "password": password,
            "role": "sales",
        },
        headers=admin_headers,
    )
    assert response.status_code == 201
    login = client.post(
        "/auth/login", data={"username": mobile, "password": password}
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_duplicate_submission_by_unrelated_user_does_not_leak_owner_lead():
    """
    Regression test: a sales user (User B) who is not the owner of an
    existing lead, and cannot otherwise view it, must never receive that
    lead's customer_name/need/source/owner_id in the response just
    because they happened to submit the same mobile number. Previously
    the API returned the full LeadResponse of the existing (User A's)
    lead, leaking User A's confidential customer data to User B and then
    404ing when User B tried to open the leaked lead id.
    """
    owner_headers = get_admin_headers()
    mobile = unique_mobile()

    original = create_lead(
        owner_headers,
        mobile,
        customer_name="Confidential Regression Customer",
    )
    assert original.status_code == 201
    owner_lead = original.json()
    assert owner_lead["customer_name"] == "Confidential Regression Customer"

    other_user_headers = _create_sales_user_and_login()
    duplicate_attempt = client.post(
        "/leads/",
        json={
            "customer_name": "Whatever The Other User Typed",
            "mobile": mobile,
            "source": "unrelated-guess",
            "need": "unrelated-guess",
        },
        headers=other_user_headers,
    )
    assert duplicate_attempt.status_code == 201
    body = duplicate_attempt.json()

    # None of the owner's confidential fields may appear anywhere in the
    # response body given back to the unrelated submitter.
    assert "customer_name" not in body
    assert "owner_id" not in body
    assert "mobile" not in body
    assert "Confidential Regression Customer" not in str(body)

    # The submitter must not be handed an id that resolves to a lead
    # they cannot view (this previously caused a confusing 404 on
    # navigation in the frontend, on top of the leak itself).
    assert "id" not in body

    # The real owner can still see their own lead untouched.
    owner_view = client.get(f"/leads/{owner_lead['id']}", headers=owner_headers)
    assert owner_view.status_code == 200
    assert owner_view.json()["customer_name"] == "Confidential Regression Customer"


def test_duplicate_submission_by_owner_still_returns_full_lead():
    """
    The redaction must only apply to unrelated users — the owner
    resubmitting their own lead's mobile number should still see the
    full, familiar LeadResponse (existing behavior, not a regression).
    """
    headers = get_admin_headers()
    mobile = unique_mobile()

    first = create_lead(headers, mobile, customer_name="Owner Resubmit Customer")
    assert first.status_code == 201
    lead_id = first.json()["id"]

    second = create_lead(headers, mobile, customer_name="Owner Resubmit Customer Again")
    assert second.status_code == 201
    body = second.json()
    assert body["id"] == lead_id
    assert body["customer_name"] == "Owner Resubmit Customer"
