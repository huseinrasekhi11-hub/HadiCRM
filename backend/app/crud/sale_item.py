"""
===========================================================
CRUD اقلام فروش و تجمیع «پرفروش‌ترین کالاها به ریال»
-----------------------------------------------------------
تغییر این نسخه: وضعیت موفق رسمی از «closed_won» به «final_factor»
تغییر کرده است (ثابت WON_STATUS در همین فایل، تنها نقطه‌ی تعریف).
===========================================================
"""
from datetime import datetime
from datetime import timedelta
from datetime import timezone

from sqlalchemy import and_
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.crud.activity import create_activity
from app.models.lead import Lead
from app.models.product import Product
from app.models.sale_item import SaleItem
from app.models.user import User
from app.schemas.activity import ActivityCreate

# وضعیت رسمی «فروش موفق» = صدور فاکتور/عامل نهایی
WON_STATUS = "final_factor"


def _validate_products(db: Session, items) -> None:
    """اطمینان از وجود و فعال بودن همه‌ی کالاهای ارجاع‌شده."""
    for item in items:
        product = (
            db.query(Product)
            .filter(Product.id == item.product_id)
            .first()
        )
        if product is None or not product.is_active:
            raise ValueError(f"Product {item.product_id} not found or inactive.")


def _items_total(db: Session, lead: Lead) -> int:
    total = (
        db.query(func.coalesce(func.sum(SaleItem.amount), 0))
        .filter(SaleItem.lead_id == lead.id)
        .scalar()
    )
    return int(total or 0)


def set_sale_items(
    db: Session,
    lead: Lead,
    items,
    current_user: User,
    sync_sale_amount: bool = True,
    *,
    commit: bool = True,
) -> int:
    """
    جایگزینی کامل اقلام فروش یک پرونده (رفتار هم‌توان).
    خروجی: مجموع ریالی اقلام.
    """
    _validate_products(db, items)

    (
        db.query(SaleItem)
        .filter(SaleItem.lead_id == lead.id)
        .delete(synchronize_session=False)
    )

    for item in items:
        db.add(
            SaleItem(
                lead_id=lead.id,
                product_id=item.product_id,
                amount=item.amount,
            )
        )

    total = sum(item.amount for item in items)

    if sync_sale_amount:
        lead.sale_amount = total

    create_activity(
        db,
        lead,
        current_user,
        ActivityCreate(
            activity_type="sale_item_added",
            title="ثبت اقلام فروش",
            description=(
                f"{len(items)} قلم فروش به مبلغ مجموع {total} ریال ثبت شد."
            ),
        ),
        commit=False,
    )

    if commit:
        db.commit()
        db.refresh(lead)
    return total


def add_sale_item(
    db: Session,
    lead: Lead,
    current_user: User,
    item,
) -> SaleItem:
    """
    الحاق یک قلم فروش با ادغام مقدار برای کالای تکراری.
    """
    _validate_products(db, [item])

    existing = (
        db.query(SaleItem)
        .filter(
            SaleItem.lead_id == lead.id,
            SaleItem.product_id == item.product_id,
        )
        .first()
    )

    if existing is not None:
        existing.amount = existing.amount + item.amount
        sale_item = existing
    else:
        sale_item = SaleItem(
            lead_id=lead.id,
            product_id=item.product_id,
            amount=item.amount,
        )
        db.add(sale_item)

    product = (
        db.query(Product)
        .filter(Product.id == item.product_id)
        .first()
    )

    create_activity(
        db,
        lead,
        current_user,
        ActivityCreate(
            activity_type="sale_item_added",
            title="ثبت قلم فروش",
            description=(
                f"کالای «{product.name if product else item.product_id}» "
                f"به مبلغ {item.amount} ریال ثبت شد."
            ),
        ),
        commit=False,
    )

    db.flush()

    # Keep lead.sale_amount in sync with the structured sale_items total
    # every time an item is appended, not just the first time. Previously
    # this only ran when sale_amount was still None, so a lead closed
    # with an explicit manual amount (the normal flow via the status-
    # change modal) never had its sale_amount updated when items were
    # added afterward via this endpoint — the dashboard's revenue total
    # and the itemized product total would silently disagree from then
    # on. Once sale items exist for a lead, they are the source of truth
    # for its recorded sale amount.
    lead.sale_amount = _items_total(db, lead)

    db.commit()
    db.refresh(sale_item)
    db.refresh(lead)
    return sale_item


def get_lead_sale_items(db: Session, lead: Lead) -> list[dict]:
    """اقلام فروش پرونده همراه با نام کالا."""
    rows = (
        db.query(SaleItem, Product.name)
        .outerjoin(Product, SaleItem.product_id == Product.id)
        .filter(SaleItem.lead_id == lead.id)
        .order_by(SaleItem.id.asc())
        .all()
    )

    return [
        {
            "id": item.id,
            "lead_id": item.lead_id,
            "product_id": item.product_id,
            "product_name": product_name,
            "amount": item.amount,
            "created_at": item.created_at,
        }
        for item, product_name in rows
    ]


def get_top_products_stats(db: Session, days: int | None = None) -> dict:
    """
    نمودار پرفروش‌ترین کالاها به ریال.
    فقط پرونده‌های حذف‌نشده با وضعیت رسمی فروش موفق (final_factor).
    """
    won_filters = [
        Lead.is_deleted == False,
        Lead.status == WON_STATUS,
    ]

    if days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        won_filters.append(Lead.status_updated_at.isnot(None))
        won_filters.append(Lead.status_updated_at >= cutoff)

    won_leads = db.query(Lead.id).filter(*won_filters)

    total_amount = func.coalesce(func.sum(SaleItem.amount), 0)

    rows = (
        db.query(
            Product.id,
            Product.name,
            total_amount.label("total_sales"),
            func.count(func.distinct(SaleItem.lead_id)).label("lead_count"),
        )
        .outerjoin(
            SaleItem,
            and_(
                SaleItem.product_id == Product.id,
                SaleItem.lead_id.in_(won_leads),
            ),
        )
        .filter(Product.is_active == True)
        .group_by(Product.id, Product.name)
        .order_by(total_amount.desc())
        .all()
    )

    products = [
        {
            "product_id": product_id,
            "product_name": product_name,
            "total_sales": int(total_sales or 0),
            "lead_count": int(lead_count or 0),
        }
        for product_id, product_name, total_sales, lead_count in rows
    ]

    grand_total = sum(row["total_sales"] for row in products)

    leads_with_items = (
        db.query(SaleItem.lead_id)
        .filter(SaleItem.lead_id.in_(won_leads))
        .distinct()
    )

    unattributed = (
        db.query(func.coalesce(func.sum(Lead.sale_amount), 0))
        .filter(
            *won_filters,
            Lead.sale_amount.isnot(None),
            Lead.id.notin_(leads_with_items),
        )
        .scalar()
    )

    return {
        "products": products,
        "total_sales": grand_total,
        "unattributed_amount": int(unattributed or 0),
    }
