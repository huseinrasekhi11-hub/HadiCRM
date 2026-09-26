"""
Integration tests for the advanced admin sales analytics charts.

Prerequisites (same as the rest of the suite):
  * PostgreSQL reachable via DATABASE_URL
  * Admin user exists: mobile 09120000000 / password Admin123!
  * Migrations applied: alembic upgrade head

NOTE: the test database is shared with other suites, therefore all
assertions are relative (membership / >= / consistency), never absolute.
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


def create_sales_user(headers):
    mobile = unique_mobile()
    password = "ChartPass123!"
    response = client.post(
        "/users/",
        json={
            "full_name": "Chart Test Salesperson",
            "mobile": mobile,
            "password": password,
            "role": "sales",
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json(), mobile, password


def create_lead(headers, customer_name="Chart Customer"):
    response = client.post(
        "/leads/",
        json={
            "customer_name": customer_name,
            "mobile": unique_mobile(),
            "source": "site",
            "need": "Chart analytics test",
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def close_lead_won(headers, lead_id, sale_amount):
    response = client.patch(
        f"/leads/{lead_id}/status",
        json={"status": "closed_won", "sale_amount": sale_amount},
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()


def close_lead_lost(headers, lead_id):
    response = client.patch(
        f"/leads/{lead_id}/status",
        json={"status": "closed_lost", "loss_reason": "price"},
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()


def test_manager_dashboard_no_longer_crashes():
    """ممیزی باگ: پیش از این /dashboard/ با NameError/AttributeError سقوط می‌کرد."""
    headers = get_admin_headers()
    response = client.get("/dashboard/", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert "pipeline" in body
    assert "salesperson_performance" in body
    assert "leads" in body


def test_salesperson_dashboard_works():
    admin_headers = get_admin_headers()
    sales_user, mobile, password = create_sales_user(admin_headers)
    sales_headers = login(mobile, password)

    response = client.get("/dashboard/", headers=sales_headers)
    assert response.status_code == 200
    body = response.json()
    assert "today_followups" in body
    assert "my_leads" in body


def test_daily_sales_returns_zero_filled_series():
    headers = get_admin_headers()

    lead = create_lead(headers)
    close_lead_won(headers, lead["id"], sale_amount=125000000)

    response = client.get(
        "/dashboard/charts/daily-sales",
        params={"days": 30},
        headers=headers,
    )
    assert response.status_code == 200

    series = response.json()
    assert len(series) == 30
    assert all("label" in point and "amount" in point and "count" in point for point in series)

    # فروش امروز باید شامل مبلغ ثبت‌شده باشد (یا بیشتر، به‌خاطر داده‌های قبلی)
    today_amount = series[-1]["amount"]
    today_count = series[-1]["count"]
    assert today_amount >= 125000000
    assert today_count >= 1


def test_sales_by_user_aggregates_amount_and_average():
    headers = get_admin_headers()

    lead = create_lead(headers, customer_name="Sales By User Customer")
    close_lead_won(headers, lead["id"], sale_amount=50000000)

    response = client.get("/dashboard/charts/sales-by-user", headers=headers)
    assert response.status_code == 200

    rows = response.json()
    assert rows, "Expected at least one user row"

    admin_row = [row for row in rows if row["user_id"] == 1]
    assert admin_row, "Admin (owner of the test lead) must appear in sales-by-user"

    row = admin_row[0]
    assert row["full_name"] == "System Administrator"
    assert row["won_count"] >= 1
    assert row["total_sales"] >= 50000000
    assert row["average_sale"] >= 1
    # میانگین = مجموع / تعداد → باید سازگار باشد
    assert row["average_sale"] == int(row["total_sales"] / row["won_count"])


def test_sales_by_user_supports_time_window():
    headers = get_admin_headers()

    lead = create_lead(headers)
    close_lead_won(headers, lead["id"], sale_amount=10000000)

    response = client.get(
        "/dashboard/charts/sales-by-user",
        params={"days": 7},
        headers=headers,
    )
    assert response.status_code == 200

    admin_row = [row for row in response.json() if row["user_id"] == 1][0]
    assert admin_row["total_sales"] >= 10000000


def test_leads_by_user_breakdown():
    headers = get_admin_headers()

    open_lead = create_lead(headers)
    won_lead = create_lead(headers)
    lost_lead = create_lead(headers)
    close_lead_won(headers, won_lead["id"], sale_amount=5000000)
    close_lead_lost(headers, lost_lead["id"])

    response = client.get("/dashboard/charts/leads-by-user", headers=headers)
    assert response.status_code == 200

    rows = response.json()
    admin_row = [row for row in rows if row["user_id"] == 1][0]

    assert admin_row["total_leads"] >= 3
    assert admin_row["won_leads"] >= 1
    assert admin_row["lost_leads"] >= 1
    assert admin_row["open_leads"] >= 1
    assert (
        admin_row["total_leads"]
        == admin_row["open_leads"] + admin_row["won_leads"] + admin_row["lost_leads"]
    )


def test_conversion_stats_consistency():
    headers = get_admin_headers()

    won_lead = create_lead(headers)
    close_lead_won(headers, won_lead["id"], sale_amount=7000000)

    response = client.get("/dashboard/charts/conversion", headers=headers)
    assert response.status_code == 200

    body = response.json()
    assert body["total_leads"] >= 1
    assert body["won_leads"] >= 1
    assert body["total_leads"] == (
        body["open_leads"] + body["won_leads"] + body["lost_leads"]
    )
    assert 0 <= body["conversion_rate"] <= 100


def test_referrals_charts_after_assignment():
    headers = get_admin_headers()
    sales_user, _, _ = create_sales_user(headers)

    lead = create_lead(headers)
    assign_response = client.patch(
        f"/leads/{lead['id']}/assign",
        json={"owner_id": sales_user["id"], "note": "referral chart test"},
        headers=headers,
    )
    assert assign_response.status_code == 200

    # بیشترین ارجاع‌های دریافت‌شده
    received = client.get("/dashboard/charts/referrals-received", headers=headers)
    assert received.status_code == 200

    received_rows = received.json()
    sales_row = [row for row in received_rows if row["user_id"] == sales_user["id"]]
    assert sales_row, "Assigned user must appear in referrals-received"
    assert sales_row[0]["received_count"] >= 1
    assert sales_row[0]["full_name"] == "Chart Test Salesperson"

    # ارجاع‌های بین کاربران (ادمین → فروش)
    pairs = client.get("/dashboard/charts/referrals-between-users", headers=headers)
    assert pairs.status_code == 200

    pair_rows = pairs.json()
    matching = [
        row for row in pair_rows
        if row["from_user_id"] == 1 and row["to_user_id"] == sales_user["id"]
    ]
    assert matching, "admin -> sales referral pair must exist"
    assert matching[0]["count"] >= 1
    assert matching[0]["from_full_name"] == "System Administrator"
    assert matching[0]["to_full_name"] == "Chart Test Salesperson"


def test_referrals_ignore_initial_self_assignment():
    """خود-ارجاعیِ اولیه‌ی پرونده (ایجاد) نباید به عنوان ارجاع شمرده شود."""
    headers = get_admin_headers()

    create_lead(headers)

    pairs = client.get("/dashboard/charts/referrals-between-users", headers=headers)
    assert pairs.status_code == 200

    self_pairs = [row for row in pairs.json() if row["from_user_id"] == row["to_user_id"]]
    assert self_pairs == []


def test_sales_trend_granularities():
    headers = get_admin_headers()

    lead = create_lead(headers)
    close_lead_won(headers, lead["id"], sale_amount=20000000)

    for granularity in ("day", "week", "month"):
        response = client.get(
            "/dashboard/charts/sales-trend",
            params={"days": 90, "granularity": granularity},
            headers=headers,
        )
        assert response.status_code == 200

        series = response.json()
        assert series, f"Trend series must not be empty for {granularity}"
        total_amount = sum(point["amount"] for point in series)
        assert total_amount >= 20000000


def test_chart_endpoints_require_admin_role():
    admin_headers = get_admin_headers()
    sales_user, mobile, password = create_sales_user(admin_headers)
    sales_headers = login(mobile, password)

    endpoints = [
        "/dashboard/charts/daily-sales",
        "/dashboard/charts/sales-by-user",
        "/dashboard/charts/leads-by-user",
        "/dashboard/charts/conversion",
        "/dashboard/charts/referrals-received",
        "/dashboard/charts/referrals-between-users",
        "/dashboard/charts/sales-trend",
    ]

    for endpoint in endpoints:
        # بدون توکن
        assert client.get(endpoint).status_code == 401, endpoint
        # کاربر فروش
        assert client.get(endpoint, headers=sales_headers).status_code == 403, endpoint
        # ادمین
        assert client.get(endpoint, headers=admin_headers).status_code == 200, endpoint
