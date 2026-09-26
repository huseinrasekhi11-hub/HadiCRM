"""
Integration tests for the product sales aggregation feature.

Prerequisites (same as the rest of the suite):
  * PostgreSQL reachable via DATABASE_URL
  * Admin user exists: mobile 09120000000 / password Admin123!
  * Migrations applied: alembic upgrade head (products catalog seeded)
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


def get_products(headers):
    response = client.get("/products/", headers=headers)
    assert response.status_code == 200
    return response.json()


def product_id_by_name(headers, name):
    products = get_products(headers)
    matches = [p for p in products if p["name"] == name]
    assert matches, f"Catalog product '{name}' must exist after migration seed"
    return matches[0]["id"]


def create_lead(headers):
    response = client.post(
        "/leads/",
        json={
            "customer_name": "Product Sales Customer",
            "mobile": unique_mobile(),
            "source": "site",
            "need": "Product chart test",
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def close_won_with_items(headers, lead_id, items, sale_amount=None):
    payload = {"status": "closed_won", "sale_items": items}
    if sale_amount is not None:
        payload["sale_amount"] = sale_amount
    response = client.patch(f"/leads/{lead_id}/status", json=payload, headers=headers)
    assert response.status_code == 200
    return response.json()


def test_products_catalog_is_seeded():
    headers = get_admin_headers()
    products = get_products(headers)

    names = [p["name"] for p in products]
    for expected in (
        "داکت اسپیلت",
        "فن کوئل",
        "چیلر",
        "اسپیلت",
        "کولر آبی",
        "پکیج",
        "رادیاتور",
        "شیرآلات",
        "هود سینک گاز",
        "سایر",
    ):
        assert expected in names


def test_products_endpoint_requires_authentication():
    assert client.get("/products/").status_code == 401


def test_close_won_with_sale_items_syncs_sale_amount():
    headers = get_admin_headers()
    lead = create_lead(headers)

    ducted_id = product_id_by_name(headers, "داکت اسپیلت")
    chiller_id = product_id_by_name(headers, "چیلر")

    body = close_won_with_items(
        headers,
        lead["id"],
        [
            {"product_id": ducted_id, "amount": 120000000},
            {"product_id": chiller_id, "amount": 80000000},
        ],
    )

    assert body["status"] == "final_factor"  # canonical since rename; closed_won is an accepted input alias
    # مبلغ کل باید برابر مجموع اقلام باشد (۲۰۰ میلیون ریال)
    assert body["sale_amount"] == 200000000

    items_response = client.get(f"/leads/{lead['id']}/sale-items", headers=headers)
    assert items_response.status_code == 200

    items = items_response.json()
    assert len(items) == 2
    assert {item["product_name"] for item in items} == {"داکت اسپیلت", "چیلر"}
    assert sum(item["amount"] for item in items) == 200000000


def test_explicit_sale_amount_is_preserved_over_items_sum():
    headers = get_admin_headers()
    lead = create_lead(headers)

    package_id = product_id_by_name(headers, "پکیج")

    body = close_won_with_items(
        headers,
        lead["id"],
        [{"product_id": package_id, "amount": 50000000}],
        sale_amount=65000000,  # مبلغ دستی شامل نصب/متعلقات
    )

    assert body["sale_amount"] == 65000000


def test_sale_items_rejected_for_non_won_status():
    headers = get_admin_headers()
    lead = create_lead(headers)
    radiator_id = product_id_by_name(headers, "رادیاتور")

    response = client.patch(
        f"/leads/{lead['id']}/status",
        json={
            "status": "contacted",
            "sale_items": [{"product_id": radiator_id, "amount": 1000000}],
        },
        headers=headers,
    )
    assert response.status_code == 422


def test_invalid_product_id_rejected():
    headers = get_admin_headers()
    lead = create_lead(headers)

    response = client.patch(
        f"/leads/{lead['id']}/status",
        json={
            "status": "closed_won",
            "sale_items": [{"product_id": 999999, "amount": 1000}],
        },
        headers=headers,
    )
    assert response.status_code == 400


def test_append_sale_item_merges_same_product():
    headers = get_admin_headers()
    lead = create_lead(headers)

    split_id = product_id_by_name(headers, "اسپیلت")

    first = client.post(
        f"/leads/{lead['id']}/sale-items",
        json={"product_id": split_id, "amount": 30000000},
        headers=headers,
    )
    assert first.status_code == 201

    second = client.post(
        f"/leads/{lead['id']}/sale-items",
        json={"product_id": split_id, "amount": 20000000},
        headers=headers,
    )
    assert second.status_code == 201

    items = client.get(f"/leads/{lead['id']}/sale-items", headers=headers).json()
    split_items = [item for item in items if item["product_id"] == split_id]
    # ادغام شده: فقط یک ردیف با مجموع مبلغ
    assert len(split_items) == 1
    assert split_items[0]["amount"] == 50000000


def test_append_sale_item_after_close_resyncs_sale_amount():
    """
    Regression test: closing a lead with a manual sale_amount (the normal
    flow via the status-change modal) and then adding a structured sale
    item afterward via the "sales tab" endpoint must keep lead.sale_amount
    in sync with the recorded items. Previously add_sale_item only ever
    set sale_amount when it was still None, so a manually-entered amount
    was never updated when items were appended later — the dashboard's
    revenue total and the itemized product-sales total would silently
    and permanently disagree for that deal.
    """
    headers = get_admin_headers()
    lead = create_lead(headers)

    # Close won with a manual amount and no structured items yet —
    # mirrors a rep typing an amount in the status-change modal.
    closed = close_won_with_items(headers, lead["id"], items=[], sale_amount=65000000)
    assert closed["sale_amount"] == 65000000

    package_id = product_id_by_name(headers, "پکیج")
    added = client.post(
        f"/leads/{lead['id']}/sale-items",
        json={"product_id": package_id, "amount": 20000000},
        headers=headers,
    )
    assert added.status_code == 201

    lead_after = client.get(f"/leads/{lead['id']}", headers=headers).json()
    # Once an item exists, the item total is the source of truth for
    # sale_amount — it must no longer be stuck at the old manual figure.
    assert lead_after["sale_amount"] == 20000000

    # Appending a second item must keep resyncing to the running total,
    # not just the first time an item is added.
    second_added = client.post(
        f"/leads/{lead['id']}/sale-items",
        json={"product_id": package_id, "amount": 5000000},
        headers=headers,
    )
    assert second_added.status_code == 201
    lead_after_second = client.get(f"/leads/{lead['id']}", headers=headers).json()
    assert lead_after_second["sale_amount"] == 25000000


def test_top_products_chart_aggregates_rial_amounts():
    headers = get_admin_headers()

    fancoil_id = product_id_by_name(headers, "فن کوئل")

    lead = create_lead(headers)
    close_won_with_items(
        headers,
        lead["id"],
        [{"product_id": fancoil_id, "amount": 45000000}],
    )

    response = client.get("/dashboard/charts/top-products", headers=headers)
    assert response.status_code == 200

    body = response.json()
    assert "products" in body
    assert "total_sales" in body
    assert "unattributed_amount" in body

    # همه‌ی کالاهای کاتالوگ حاضرند (حتی با فروش صفر)
    product_names = [row["product_name"] for row in body["products"]]
    assert "فن کوئل" in product_names
    assert "چیلر" in product_names

    fancoil_row = [row for row in body["products"] if row["product_name"] == "فن کوئل"][0]
    assert fancoil_row["total_sales"] >= 45000000
    assert fancoil_row["lead_count"] >= 1

    assert body["total_sales"] >= 45000000

    # مرتب‌شده بر اساس مبلغ فروش (نزولی)
    amounts = [row["total_sales"] for row in body["products"]]
    assert amounts == sorted(amounts, reverse=True)


def test_unattributed_amount_reports_legacy_sales():
    headers = get_admin_headers()

    # فروش موفق قدیمی: فقط مبلغ کل، بدون اقلام ساختاریافته
    lead = create_lead(headers)
    response = client.patch(
        f"/leads/{lead['id']}/status",
        json={
            "status": "closed_won",
            "sale_amount": 99000000,
            "sold_products": "کولر آبی ۷۰۰۰",
        },
        headers=headers,
    )
    assert response.status_code == 200

    body = client.get("/dashboard/charts/top-products", headers=headers).json()
    assert body["unattributed_amount"] >= 99000000


def test_top_products_chart_permissions():
    admin_headers = get_admin_headers()

    # بدون توکن
    assert client.get("/dashboard/charts/top-products").status_code == 401

    # کاربر فروش
    sales_mobile = unique_mobile()
    create_user_response = client.post(
        "/users/",
        json={
            "full_name": "Product Chart Salesperson",
            "mobile": sales_mobile,
            "password": "ProductPass123!",
            "role": "sales",
        },
        headers=admin_headers,
    )
    assert create_user_response.status_code == 201
    sales_headers = login(sales_mobile, "ProductPass123!")

    assert (
        client.get("/dashboard/charts/top-products", headers=sales_headers).status_code
        == 403
    )


def test_admin_can_create_product_and_duplicate_rejected():
    headers = get_admin_headers()

    new_name = f"محصول تست {str(uuid4().int)[:6]}"

    created = client.post("/products/", json={"name": new_name}, headers=headers)
    assert created.status_code == 201
    assert created.json()["name"] == new_name

    duplicate = client.post("/products/", json={"name": new_name}, headers=headers)
    assert duplicate.status_code == 400


def test_sales_user_cannot_create_product():
    admin_headers = get_admin_headers()

    sales_mobile = unique_mobile()
    client.post(
        "/users/",
        json={
            "full_name": "No Product Create User",
            "mobile": sales_mobile,
            "password": "ProductPass123!",
            "role": "sales",
        },
        headers=admin_headers,
    )
    sales_headers = login(sales_mobile, "ProductPass123!")

    response = client.post("/products/", json={"name": "غیرمجاز"}, headers=sales_headers)
    assert response.status_code == 403
