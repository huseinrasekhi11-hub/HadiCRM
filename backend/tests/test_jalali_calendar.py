"""
Integration + unit tests for Jalali calendar backend support.

Prerequisites (same as the rest of the suite):
  * PostgreSQL reachable via DATABASE_URL
  * Admin user exists: mobile 09120000000 / password Admin123!
  * Dependencies installed: pip install -r requirements.txt (jdatetime)
"""
import re
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core import jalali
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


def create_lead(headers):
    response = client.post(
        "/leads/",
        json={
            "customer_name": "Jalali Test Customer",
            "mobile": unique_mobile(),
            "source": "site",
            "need": "Jalali calendar test",
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


# ---------------------------------------------------------------
# Unit: utility module
# ---------------------------------------------------------------
def test_parse_jalali_date_nowruz_anchor():
    """نوروز ۱۴۰۵ باید دقیقاً ۲۰۲۶-۰۳-۲۱ باشد."""
    parsed = jalali.parse_jalali_date("1405/01/01")
    assert parsed.tzinfo is not None

    tehran_date = parsed.astimezone(jalali.TEHRAN_TZ).date()
    assert (tehran_date.year, tehran_date.month, tehran_date.day) == (2026, 3, 21)


def test_jalali_parse_format_roundtrip():
    parsed = jalali.parse_jalali_date("1405/05/10")
    assert jalali.format_jalali_date(parsed) == "1405/05/10"

    parsed_dash = jalali.parse_jalali_date("1405-05-10")
    assert jalali.format_jalali_date(parsed_dash) == "1405/05/10"


def test_parse_jalali_with_time():
    parsed = jalali.parse_jalali_date("1405/05/10 15:30")
    tehran = parsed.astimezone(jalali.TEHRAN_TZ)
    assert tehran.hour == 15
    assert tehran.minute == 30
    assert jalali.format_jalali_datetime(parsed) == "1405/05/10 15:30"


def test_parse_jalali_rejects_invalid_values():
    for bad in ("", "1405/13/01", "1405/05/32", "not-a-date", "1405/05"):
        with pytest.raises(ValueError):
            jalali.parse_jalali_date(bad)


def test_ensure_aware_assumes_tehran_for_naive():
    naive = datetime(2026, 3, 21, 12, 0, 0)
    aware = jalali.ensure_aware(naive)
    assert aware.tzinfo is not None
    assert aware.astimezone(jalali.TEHRAN_TZ).hour == 12


def test_jalali_today_bounds_span_one_day():
    start, end = jalali.jalali_today_bounds_utc()
    assert end - start == timedelta(days=1)
    assert start <= datetime.now(timezone.utc) <= end


# ---------------------------------------------------------------
# API: chart endpoints with calendar parameter
# ---------------------------------------------------------------
def test_daily_sales_jalali_labels_and_zero_fill():
    headers = get_admin_headers()

    lead = create_lead(headers)
    close = client.patch(
        f"/leads/{lead['id']}/status",
        json={"status": "final_factor", "sale_amount": 77000000},
        headers=headers,
    )
    assert close.status_code == 200

    response = client.get(
        "/dashboard/charts/daily-sales",
        params={"days": 30, "calendar": "jalali"},
        headers=headers,
    )
    assert response.status_code == 200

    series = response.json()
    assert len(series) == 30

    for point in series:
        assert re.fullmatch(r"\d{4}/\d{2}/\d{2}", point["label"]), point["label"]

    # فروش امروزِ جلالی باید شامل مبلغ ثبت‌شده باشد
    assert series[-1]["amount"] >= 77000000
    assert series[-1]["count"] >= 1


def test_daily_sales_gregorian_labels_unchanged_by_default():
    headers = get_admin_headers()

    response = client.get(
        "/dashboard/charts/daily-sales",
        params={"days": 14},
        headers=headers,
    )
    assert response.status_code == 200

    series = response.json()
    assert len(series) == 14
    for point in series:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", point["label"]), point["label"]


def test_daily_sales_accepts_jalali_date_bounds():
    headers = get_admin_headers()

    lead = create_lead(headers)
    client.patch(
        f"/leads/{lead['id']}/status",
        json={"status": "final_factor", "sale_amount": 31000000},
        headers=headers,
    )

    today_jalali = jalali.format_jalali_date(datetime.now(timezone.utc))
    tomorrow_jalali = jalali.format_jalali_date(
        datetime.now(timezone.utc) + timedelta(days=1)
    )

    response = client.get(
        "/dashboard/charts/daily-sales",
        params={
            "calendar": "jalali",
            "date_from": today_jalali,
            "date_to": tomorrow_jalali,
        },
        headers=headers,
    )
    assert response.status_code == 200

    series = response.json()
    assert any(point["label"] == today_jalali for point in series)
    today_point = [p for p in series if p["label"] == today_jalali][0]
    assert today_point["amount"] >= 31000000


def test_daily_sales_rejects_invalid_date():
    headers = get_admin_headers()
    response = client.get(
        "/dashboard/charts/daily-sales",
        params={"date_from": "not-a-date"},
        headers=headers,
    )
    assert response.status_code == 400


def test_sales_trend_jalali_month_labels():
    headers = get_admin_headers()

    lead = create_lead(headers)
    client.patch(
        f"/leads/{lead['id']}/status",
        json={"status": "final_factor", "sale_amount": 18000000},
        headers=headers,
    )

    response = client.get(
        "/dashboard/charts/sales-trend",
        params={"days": 90, "granularity": "month", "calendar": "jalali"},
        headers=headers,
    )
    assert response.status_code == 200

    series = response.json()
    assert series, "Jalali monthly trend must not be empty"

    for point in series:
        assert re.fullmatch(r"\d{4}/\d{2}", point["label"]), point["label"]

    assert sum(point["amount"] for point in series) >= 18000000


def test_sales_trend_jalali_day_labels():
    headers = get_admin_headers()

    lead = create_lead(headers)
    client.patch(
        f"/leads/{lead['id']}/status",
        json={"status": "final_factor", "sale_amount": 9000000},
        headers=headers,
    )

    response = client.get(
        "/dashboard/charts/sales-trend",
        params={"days": 30, "granularity": "day", "calendar": "jalali"},
        headers=headers,
    )
    assert response.status_code == 200

    series = response.json()
    assert series
    for point in series:
        assert re.fullmatch(r"\d{4}/\d{2}/\d{2}", point["label"]), point["label"]


def test_calendar_parameter_validation():
    headers = get_admin_headers()
    response = client.get(
        "/dashboard/charts/daily-sales",
        params={"calendar": "hijri-lunar"},
        headers=headers,
    )
    assert response.status_code == 422


# ---------------------------------------------------------------
# Follow-up filtering on the Tehran (Jalali) day
# ---------------------------------------------------------------
def test_today_followup_smart_filter_uses_tehran_day():
    headers = get_admin_headers()
    lead = create_lead(headers)

    followup_at = datetime.now(timezone.utc).isoformat()
    patch = client.patch(
        f"/leads/{lead['id']}/followup",
        json={"next_follow_up": followup_at},
        headers=headers,
    )
    assert patch.status_code == 200

    response = client.get(
        "/leads/",
        params={"smart_filter": "today_followup"},
        headers=headers,
    )
    assert response.status_code == 200
    assert any(item["id"] == lead["id"] for item in response.json())


# ---------------------------------------------------------------
# status_updated_at must be consistently naive Tehran wall-clock time
# ---------------------------------------------------------------
def test_status_updated_at_matches_model_default_timezone_convention():
    """
    Regression test: leads.status_updated_at is documented (see
    app/core/jalali.py module docstring) as always holding a naive
    Tehran-local wall-clock value, exactly like the column's own
    default (get_tehran_time). Previously update_lead_status wrote
    datetime.now(timezone.utc) instead — since the column has no
    timezone=True, the database silently drops tzinfo on persist, so
    a Tehran-local value and a UTC value land as two different naive
    numbers (~3.5 hours apart) for the same real instant, depending
    purely on which code path last touched the lead's status. This
    corrupts day-bucketing in the sales-trend/daily-sales Jalali
    calendar reports.

    We can't observe status_updated_at through the API (it isn't in
    LeadResponse), so this test reads it directly from the database,
    the same way the dashboard queries do.
    """
    from app.core.jalali import naive_tehran_now
    from app.database.database import SessionLocal
    from app.models.lead import Lead

    headers = get_admin_headers()
    lead = create_lead(headers)

    # A fresh lead's status_updated_at comes from the column's own
    # default (get_tehran_time) — this is our Tehran-wall-clock baseline.
    db = SessionLocal()
    try:
        db_lead = db.query(Lead).filter(Lead.id == lead["id"]).first()
        baseline = db_lead.status_updated_at
    finally:
        db.close()
    assert baseline is not None

    # Now trigger an explicit status change through the real API — the
    # exact code path that used to write UTC instead of Tehran time.
    before_change = naive_tehran_now()
    response = client.patch(
        f"/leads/{lead['id']}/status",
        json={"status": "contacted"},
        headers=headers,
    )
    assert response.status_code == 200
    after_change = naive_tehran_now()

    db2 = SessionLocal()
    try:
        db_lead_after = db2.query(Lead).filter(Lead.id == lead["id"]).first()
        stored = db_lead_after.status_updated_at
    finally:
        db2.close()

    # The value written by the explicit status-change path must fall
    # within the Tehran-wall-clock window we bracketed it with — not
    # ~3.5 hours off, which is what a UTC-instead-of-Tehran write would
    # produce.
    assert before_change <= stored <= after_change, (
        f"status_updated_at={stored} is not within the Tehran wall-clock "
        f"window [{before_change}, {after_change}] — looks like it was "
        "written in a different timezone convention than the column's "
        "own default."
    )


def test_dashboard_today_bounds_align_with_tehran_calendar_day():
    """
    Regression test: app.crud.dashboard._today_bounds() must bracket the
    Tehran calendar day (midnight to midnight, Asia/Tehran), not the UTC
    calendar day. Previously it computed UTC midnight directly, so for
    roughly 3.5 hours of every real day (UTC midnight to Tehran midnight,
    i.e. late evening Tehran time) items due "today" in Tehran would be
    excluded from the dashboard's today_followups/today_tasks counts, or
    items from the tail end of Tehran's previous day would be wrongly
    included — a straightforward, unconditional day-boundary shift, not
    a rare edge case.
    """
    from app.core import jalali
    from app.crud.dashboard import _today_bounds

    now, today_start, today_end = _today_bounds()

    # Both bounds must be tz-aware (comparable against the app's aware
    # DateTime(timezone=True) columns like Task.due_at / Lead.next_follow_up).
    assert today_start.tzinfo is not None
    assert today_end.tzinfo is not None

    # Converted to Tehran local time, the window must be exactly
    # midnight-to-midnight — not shifted by the UTC/Tehran offset.
    tehran_start = jalali.to_tehran(today_start)
    tehran_end = jalali.to_tehran(today_end)

    assert (tehran_start.hour, tehran_start.minute, tehran_start.second) == (0, 0, 0)
    assert (tehran_end.hour, tehran_end.minute, tehran_end.second) == (0, 0, 0)
    assert (tehran_end - tehran_start) == timedelta(days=1)

    # "now" must actually fall inside its own day's bounds (sanity check
    # that we didn't accidentally return some other day's window).
    assert today_start <= now < today_end
