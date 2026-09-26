"""
اسکریپت تولید محصولات و اقلام فروش (Sale Line Items) آزمایشی.

این اسکریپت باید *بعد از* seed_fake_data.py اجرا شود، چون به لیدهایی
با وضعیت «فروش موفق» (final_factor) نیاز دارد تا به آن‌ها کالا و مبلغ
فروش متصل کند.

کاری که انجام می‌دهد:
  1) چند محصول واقعی در جدول products می‌سازد (در صورت نبود).
  2) برای هر لید با وضعیت final_factor، ۱ تا ۳ قلم کالا با مبلغ می‌سازد.
  3) مبلغ Lead.sale_amount را با مجموع اقلام هماهنگ می‌کند تا نمودارها
     و جمع کل‌ها (داشبورد + گزارش محصولات) دقیقاً همخوانی داشته باشند.

اجرا:
    python seed_sales_and_products.py
"""
import random
from sqlalchemy import func

from app.database.database import SessionLocal
from app.models.lead import Lead
from app.models.product import Product
from app.models.sale_item import SaleItem

db = SessionLocal()

# ----------------------------------------------------------------
# 1) کاتالوگ محصولات
# ----------------------------------------------------------------
PRODUCT_NAMES = [
    "بسته‌ی پایه نرم‌افزار",
    "بسته‌ی حرفه‌ای نرم‌افزار",
    "بسته‌ی سازمانی نرم‌افزار",
    "لایسنس اضافه کاربر",
    "پشتیبانی سالانه",
    "آموزش اختصاصی تیم",
    "ماژول گزارش‌گیری پیشرفته",
    "ماژول اتصال به حسابداری",
    "سرویس مهاجرت داده",
    "بسته‌ی سخت‌افزاری همراه",
]

# قیمت پایه‌ی هر محصول (ریال) — برای تولید مبالغ واقع‌گرایانه
PRODUCT_BASE_PRICE = {
    "بسته‌ی پایه نرم‌افزار": 3_500_000,
    "بسته‌ی حرفه‌ای نرم‌افزار": 8_500_000,
    "بسته‌ی سازمانی نرم‌افزار": 22_000_000,
    "لایسنس اضافه کاربر": 900_000,
    "پشتیبانی سالانه": 4_200_000,
    "آموزش اختصاصی تیم": 2_800_000,
    "ماژول گزارش‌گیری پیشرفته": 3_100_000,
    "ماژول اتصال به حسابداری": 2_600_000,
    "سرویس مهاجرت داده": 1_900_000,
    "بسته‌ی سخت‌افزاری همراه": 6_400_000,
}

products = {}
for name in PRODUCT_NAMES:
    existing = db.query(Product).filter(Product.name == name).first()
    if existing:
        products[name] = existing
        continue
    product = Product(name=name, is_active=True)
    db.add(product)
    db.flush()
    products[name] = product

db.commit()
print(f"✅ {len(products)} محصول آماده شد (موجود یا تازه‌ساخته‌شده).")

product_list = list(products.values())

# ----------------------------------------------------------------
# 2) اتصال اقلام فروش به لیدهای «فروش موفق» (final_factor)
# ----------------------------------------------------------------
won_leads = db.query(Lead).filter(Lead.status == "final_factor").all()

if not won_leads:
    print("⚠️ هیچ لیدی با وضعیت «فروش موفق» (final_factor) پیدا نشد.")
    print("   ابتدا seed_fake_data.py را اجرا کنید تا لیدهای فروخته‌شده ساخته شوند.")
    db.close()
    raise SystemExit(0)

random.seed(7)

items_created = 0
leads_updated = 0

for lead in won_leads:
    # اگر این لید قبلاً قلم فروش دارد، از آن عبور کن (برای اجرای چندباره‌ی امن)
    already_has_items = (
        db.query(SaleItem).filter(SaleItem.lead_id == lead.id).first()
    )
    if already_has_items:
        continue

    num_items = random.randint(1, 3)
    chosen_products = random.sample(product_list, k=min(num_items, len(product_list)))

    total_for_lead = 0
    for product in chosen_products:
        base_price = PRODUCT_BASE_PRICE.get(product.name, 2_000_000)
        # کمی نوسان قیمت برای واقعی‌تر شدن (±20%)
        amount = int(base_price * random.uniform(0.8, 1.2))
        amount = round(amount, -4)  # رند به ده‌هزار تومان نزدیک‌تر

        sale_item = SaleItem(
            lead_id=lead.id,
            product_id=product.id,
            amount=amount,
        )
        db.add(sale_item)
        total_for_lead += amount
        items_created += 1

    # هماهنگ کردن مبلغ فروش لید با مجموع اقلام، تا نمودارها یکسان باشند
    lead.sale_amount = total_for_lead
    lead.sold_products = "، ".join(p.name for p in chosen_products)
    leads_updated += 1

db.commit()
db.close()

print(f"✅ {items_created} قلم فروش برای {leads_updated} لید «فروش موفق» ساخته شد.")
print("\n🎉 اکنون می‌توانید گزارش «پرفروش‌ترین کالاها» و ارقام فروش داشبورد را بررسی کنید.")
