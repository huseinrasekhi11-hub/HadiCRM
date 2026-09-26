from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def get_admin_headers():
    response = client.post(
        "/auth/login",
        data={
            "username": "09120000000",
            "password": "Admin123!",
        },
    )
    token = response.json()["access_token"]

    return {"Authorization": f"Bearer {token}"}


def test_create_lead_assigns_current_user_as_owner():
    headers = get_admin_headers()
    mobile = f"0912{str(uuid4().int)[:7]}"

    response = client.post(
        "/leads/",
        json={
            "customer_name": "Lead Test Customer",
            "mobile": mobile,
            "source": "site",
            "need": "Needs a CRM follow-up",
        },
        headers=headers,
    )

    assert response.status_code == 201

    body = response.json()

    assert body["customer_name"] == "Lead Test Customer"
    assert body["mobile"] == mobile
    assert body["source"] == "site"
    assert body["need"] == "Needs a CRM follow-up"
    assert body["status"] == "new"
    assert body["created_by_id"] == 1
    assert body["owner_id"] == 1


def test_my_leads_requires_authentication():
    response = client.get("/leads/my")

    assert response.status_code == 401


def test_my_leads_contains_created_lead():
    headers = get_admin_headers()
    mobile = f"0912{str(uuid4().int)[:7]}"

    client.post(
        "/leads/",
        json={
            "customer_name": "Visible Lead",
            "mobile": mobile,
            "source": "instagram",
            "need": None,
        },
        headers=headers,
    )

    response = client.get("/leads/my", headers=headers)

    assert response.status_code == 200
    assert any(lead["mobile"] == mobile for lead in response.json())


def test_get_lead_detail_returns_owned_lead():
    headers = get_admin_headers()
    mobile = f"0912{str(uuid4().int)[:7]}"

    create_response = client.post(
        "/leads/",
        json={
            "customer_name": "Detail Lead",
            "mobile": mobile,
            "source": "site",
            "need": "Detail check",
        },
        headers=headers,
    )
    lead_id = create_response.json()["id"]

    response = client.get(f"/leads/{lead_id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["id"] == lead_id
    assert response.json()["mobile"] == mobile


def test_update_lead_status_changes_status():
    headers = get_admin_headers()
    mobile = f"0912{str(uuid4().int)[:7]}"

    create_response = client.post(
        "/leads/",
        json={
            "customer_name": "Status Lead",
            "mobile": mobile,
            "source": "referral",
            "need": "Status check",
        },
        headers=headers,
    )
    lead_id = create_response.json()["id"]

    response = client.patch(
        f"/leads/{lead_id}/status",
        json={"status": "contacted"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "contacted"


def test_create_lead_adds_created_activity_to_timeline():
    headers = get_admin_headers()
    mobile = f"0912{str(uuid4().int)[:7]}"

    create_response = client.post(
        "/leads/",
        json={
            "customer_name": "Timeline Lead",
            "mobile": mobile,
            "source": "site",
            "need": "Timeline check",
        },
        headers=headers,
    )
    lead_id = create_response.json()["id"]

    response = client.get(f"/leads/{lead_id}/activities", headers=headers)

    assert response.status_code == 200
    assert any(
        activity["activity_type"] == "lead_created"
        for activity in response.json()
    )


def test_update_lead_status_adds_status_activity_to_timeline():
    headers = get_admin_headers()
    mobile = f"0912{str(uuid4().int)[:7]}"

    create_response = client.post(
        "/leads/",
        json={
            "customer_name": "Status Timeline Lead",
            "mobile": mobile,
            "source": "site",
            "need": "Status timeline check",
        },
        headers=headers,
    )
    lead_id = create_response.json()["id"]

    client.patch(
        f"/leads/{lead_id}/status",
        json={"status": "contacted"},
        headers=headers,
    )

    response = client.get(f"/leads/{lead_id}/activities", headers=headers)

    assert response.status_code == 200
    assert any(
        activity["activity_type"] == "status_change"
        and "new to contacted" in activity["description"]
        for activity in response.json()
    )


def test_create_manual_activity_for_lead():
    headers = get_admin_headers()
    mobile = f"0912{str(uuid4().int)[:7]}"

    create_response = client.post(
        "/leads/",
        json={
            "customer_name": "Manual Activity Lead",
            "mobile": mobile,
            "source": "instagram",
            "need": None,
        },
        headers=headers,
    )
    lead_id = create_response.json()["id"]

    # Business rule: human actions (call/meeting/message/...) must carry
    # either next_follow_up or no_followup_reason (see ActivityCreate
    # validator and the frontend LogActionModal). Verify the rule first:
    missing_followup = client.post(
        f"/leads/{lead_id}/activities",
        json={
            "activity_type": "call",
            "title": "First call",
            "description": "Customer asked for price details.",
        },
        headers=headers,
    )
    assert missing_followup.status_code == 422

    response = client.post(
        f"/leads/{lead_id}/activities",
        json={
            "activity_type": "call",
            "title": "First call",
            "description": "Customer asked for price details.",
            "no_followup_reason": "Customer will call us back.",
        },
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["activity_type"] == "call"
    assert response.json()["title"] == "First call"


def test_no_followup_reason_clears_stale_next_follow_up():
    """
    Regression test: when a rep sets a follow-up date and then later logs
    a human activity explicitly declining a further follow-up (providing
    no_followup_reason instead of next_follow_up), the lead's stale
    next_follow_up must be cleared. Previously create_activity only ever
    set lead.next_follow_up when a new value was provided and never
    cleared it, so the lead stayed permanently visible in the "overdue
    follow-up" filter even after a rep correctly declared no further
    follow-up was needed.
    """
    headers = get_admin_headers()
    mobile = f"0912{str(uuid4().int)[:7]}"

    create_response = client.post(
        "/leads/",
        json={
            "customer_name": "No Followup Clear Lead",
            "mobile": mobile,
            "source": "site",
            "need": None,
        },
        headers=headers,
    )
    lead_id = create_response.json()["id"]

    set_followup = client.post(
        f"/leads/{lead_id}/activities",
        json={
            "activity_type": "call",
            "title": "First call",
            "next_follow_up": "2026-12-25T10:00:00Z",
        },
        headers=headers,
    )
    assert set_followup.status_code == 201

    lead_with_followup = client.get(f"/leads/{lead_id}", headers=headers).json()
    assert lead_with_followup["next_follow_up"] is not None

    decline_followup = client.post(
        f"/leads/{lead_id}/activities",
        json={
            "activity_type": "call",
            "title": "Customer declined further contact",
            "next_follow_up": None,
            "no_followup_reason": "Customer asked not to be contacted again.",
        },
        headers=headers,
    )
    assert decline_followup.status_code == 201

    lead_after = client.get(f"/leads/{lead_id}", headers=headers).json()
    assert lead_after["next_follow_up"] is None


def test_system_activity_does_not_clear_existing_follow_up():
    """
    The clearing behavior above must be scoped to human actions only.
    A system-generated activity (e.g. a status change), which never
    carries next_follow_up or no_followup_reason, must leave an
    existing next_follow_up on the lead untouched.
    """
    headers = get_admin_headers()
    mobile = f"0912{str(uuid4().int)[:7]}"

    create_response = client.post(
        "/leads/",
        json={
            "customer_name": "System Activity Followup Lead",
            "mobile": mobile,
            "source": "site",
            "need": None,
        },
        headers=headers,
    )
    lead_id = create_response.json()["id"]

    set_followup = client.post(
        f"/leads/{lead_id}/activities",
        json={
            "activity_type": "call",
            "title": "Set a follow-up",
            "next_follow_up": "2026-11-01T10:00:00Z",
        },
        headers=headers,
    )
    assert set_followup.status_code == 201
    before = client.get(f"/leads/{lead_id}", headers=headers).json()
    assert before["next_follow_up"] is not None

    status_change = client.patch(
        f"/leads/{lead_id}/status",
        json={"status": "negotiating"},
        headers=headers,
    )
    assert status_change.status_code == 200

    after = client.get(f"/leads/{lead_id}", headers=headers).json()
    assert after["next_follow_up"] == before["next_follow_up"]


def test_create_manual_activity_rejects_invalid_type():
    headers = get_admin_headers()
    mobile = f"0912{str(uuid4().int)[:7]}"

    create_response = client.post(
        "/leads/",
        json={
            "customer_name": "Invalid Activity Lead",
            "mobile": mobile,
            "source": "site",
            "need": None,
        },
        headers=headers,
    )
    lead_id = create_response.json()["id"]

    response = client.post(
        f"/leads/{lead_id}/activities",
        json={
            "activity_type": "bad-type",
            "title": "Bad activity",
            "description": None,
        },
        headers=headers,
    )

    assert response.status_code == 422


def test_update_lead_status_rejects_invalid_status():
    headers = get_admin_headers()
    mobile = f"0912{str(uuid4().int)[:7]}"

    create_response = client.post(
        "/leads/",
        json={
            "customer_name": "Invalid Status Lead",
            "mobile": mobile,
            "source": "site",
            "need": None,
        },
        headers=headers,
    )
    lead_id = create_response.json()["id"]

    response = client.patch(
        f"/leads/{lead_id}/status",
        json={"status": "not-a-real-status"},
        headers=headers,
    )

    assert response.status_code == 422


def test_get_missing_lead_returns_404():
    headers = get_admin_headers()

    response = client.get("/leads/999999", headers=headers)

    assert response.status_code == 404
