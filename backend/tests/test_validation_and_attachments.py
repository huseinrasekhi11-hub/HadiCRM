"""
Regression tests for audit fixes (2026-09-22).

Covers:
  * Input validation on lead creation (previously HTTP 500 via
    StringDataRightTruncation, or silently-accepted garbage mobiles)
  * Non-negative sale_amount
  * Minimum password policy on user creation
  * Authorized attachment downloads (previously the /uploads static
    mount served every file WITHOUT authentication)
"""
import io
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def login(mobile: str, password: str):
    response = client.post(
        "/auth/login",
        data={"username": mobile, "password": password},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def get_admin_headers():
    return login("09120000000", "Admin123!")


def unique_mobile():
    return f"0912{str(uuid4().int)[:7]}"


def create_user(headers, full_name, role, password="RoleTest123!", mobile=None):
    response = client.post(
        "/users/",
        json={
            "full_name": full_name,
            "mobile": mobile or unique_mobile(),
            "password": password,
            "role": role,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------
# Lead creation validation
# ---------------------------------------------------------------
def test_create_lead_rejects_oversized_mobile_with_422_not_500():
    headers = get_admin_headers()
    response = client.post(
        "/leads/",
        json={
            "customer_name": "Oversized Mobile",
            "mobile": "9" * 40,
            "source": "site",
            "need": None,
        },
        headers=headers,
    )
    assert response.status_code == 422


def test_create_lead_rejects_oversized_customer_name_with_422_not_500():
    headers = get_admin_headers()
    response = client.post(
        "/leads/",
        json={
            "customer_name": "x" * 300,
            "mobile": unique_mobile(),
            "source": "site",
            "need": None,
        },
        headers=headers,
    )
    assert response.status_code == 422


def test_create_lead_rejects_blank_and_garbage_mobile():
    headers = get_admin_headers()
    for bad_mobile in ("", "   ", "abc123", "abc"):
        response = client.post(
            "/leads/",
            json={
                "customer_name": "Garbage Mobile",
                "mobile": bad_mobile,
                "source": "site",
                "need": None,
            },
            headers=headers,
        )
        assert response.status_code == 422, f"mobile={bad_mobile!r} -> {response.status_code}"


def test_create_lead_accepts_persian_digits_and_country_code():
    headers = get_admin_headers()
    mobile = unique_mobile()
    # Persian digits and +98 prefix must still normalize and be accepted
    persian = mobile.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
    r1 = client.post(
        "/leads/",
        json={"customer_name": "Persian Digits", "mobile": persian, "source": "site"},
        headers=headers,
    )
    assert r1.status_code == 201, r1.text
    r2 = client.post(
        "/leads/",
        json={"customer_name": "Country Code", "mobile": f"+98{mobile[1:]}", "source": "site"},
        headers=headers,
    )
    # second submission of the same number is attached as a duplicate, not rejected
    assert r2.status_code == 201, r2.text
    assert r2.json()["id"] == r1.json()["id"]


def test_negative_sale_amount_rejected():
    headers = get_admin_headers()
    lead = client.post(
        "/leads/",
        json={"customer_name": "Neg Sale", "mobile": unique_mobile(), "source": "site"},
        headers=headers,
    ).json()
    response = client.patch(
        f"/leads/{lead['id']}/status",
        json={"status": "final_factor", "sale_amount": -50000000},
        headers=headers,
    )
    assert response.status_code == 422


# ---------------------------------------------------------------
# Password policy
# ---------------------------------------------------------------
def test_weak_password_rejected_on_user_create():
    headers = get_admin_headers()
    response = client.post(
        "/users/",
        json={
            "full_name": "Weak Password",
            "mobile": unique_mobile(),
            "password": "1",
            "role": "sales",
        },
        headers=headers,
    )
    assert response.status_code == 422


# ---------------------------------------------------------------
# Authorized attachment downloads
# ---------------------------------------------------------------
def _upload_pdf(headers, lead_id):
    return client.post(
        f"/leads/{lead_id}/attachments",
        files={"file": ("contract.pdf", io.BytesIO(b"%PDF-1.4 audit-test"), "application/pdf")},
        headers=headers,
    )


def test_attachment_download_requires_auth_and_visibility():
    admin_headers = get_admin_headers()
    lead = client.post(
        "/leads/",
        json={"customer_name": "Attachment Owner", "mobile": unique_mobile(), "source": "site"},
        headers=admin_headers,
    ).json()

    upload = _upload_pdf(admin_headers, lead["id"])
    assert upload.status_code == 201, upload.text
    attachment = upload.json()

    # the raw file path is NOT served statically anymore
    raw = client.get("/" + attachment["file_path"])
    assert raw.status_code == 404

    # unauthenticated download -> 401
    anon = client.get(f"/leads/{lead['id']}/attachments/{attachment['id']}/download")
    assert anon.status_code == 401

    # owner can download, body intact
    ok = client.get(
        f"/leads/{lead['id']}/attachments/{attachment['id']}/download",
        headers=admin_headers,
    )
    assert ok.status_code == 200
    assert ok.content == b"%PDF-1.4 audit-test"

    # a different sales user cannot see (or download) the attachment
    create_user(admin_headers, "Att Other Sales", "sales")
    users = client.get("/users/", headers=admin_headers).json()
    other = [u for u in users if u["full_name"] == "Att Other Sales"][0]
    # login as the other sales user
    other_headers = login(other["mobile"], "RoleTest123!")
    forbidden = client.get(
        f"/leads/{lead['id']}/attachments/{attachment['id']}/download",
        headers=other_headers,
    )
    assert forbidden.status_code == 404

    # attachment id from another lead cannot be fetched through this lead
    mismatch = client.get(
        f"/leads/{lead['id']}/attachments/{attachment['id'] + 9999}/download",
        headers=admin_headers,
    )
    assert mismatch.status_code == 404


def test_upload_rejects_non_whitelisted_extension():
    headers = get_admin_headers()
    lead = client.post(
        "/leads/",
        json={"customer_name": "Upload Guard", "mobile": unique_mobile(), "source": "site"},
        headers=headers,
    ).json()
    response = client.post(
        f"/leads/{lead['id']}/attachments",
        files={"file": ("evil.py", io.BytesIO(b"print('pwn')"), "text/x-python")},
        headers=headers,
    )
    assert response.status_code == 400
