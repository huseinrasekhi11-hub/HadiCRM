"""
اسکریپت پاک‌سازی + بازتولید داده‌ی آزمایشی برای تست کامل داشبورد/تحلیل‌ها.

این اسکریپت ابتدا *فقط* داده‌های آزمایشیِ قبلاً ساخته‌شده توسط
seed_fake_data.py و seed_sales_and_products.py را پاک می‌کند — با تکیه
بر این نشانه‌ی امن: کاربران آزمایشی همیشه با موبایل‌های
09120000001 .. 09120000004 ساخته شده‌اند (طبق FAKE_USERS در
seed_fake_data.py). فقط لیدها/فعالیت‌ها/وظایف/اقلام فروش/ثبت‌های
تکراری/ممیزی‌های حذفی که owner یا creator یا submitted_by یا deleted_by
آن‌ها یکی از همین چهار کاربر است پاک می‌شوند — هیچ کاربر یا لید واقعی
دیگری لمس نمی‌شود.

سپس داده‌ی تازه و گسترده‌تر می‌سازد تا همه‌ی نمودارهای بخش تحلیل‌ها
(فروش روزانه، فروش/تبدیل به تفکیک کارشناس، ارجاع‌ها، پرفروش‌ترین
کالاها، روند فروش) واقعاً داده‌ی متنوع داشته باشند:
  - ۴ کارشناس فروش + ۱ مدیر (همان کاربران قبلی، حذف نمی‌شوند، فقط
    داده‌هایشان بازسازی می‌شود)
  - لیدها روی ۹۰ روز گذشته پخش می‌شوند (نه فقط ۴۵ روز)، با نرخ فروش
    متفاوت برای هر کارشناس تا نمودار «فروش به تفکیک کارشناس» یکنواخت
    به نظر نرسد
  - محصولات واقعی کسب‌وکار (هادی تهویه — تجهیزات تهویه مطبوع) به‌جای
    بسته‌های نرم‌افزاری قبلی
  - ارجاع بین کارشناسان (referred_by/referred_to روی برخی لیدها) تا
    نمودارهای «بیشترین ارجاع‌دهنده» و «ارجاع بین کاربران» داده داشته باشند
  - چند ثبت تکراری (LeadSubmission) روی چند لید تا صفحه‌ی «سابقه‌ی
    ثبت‌های تکراری» هم خالی نباشد
  - چند حذف آزمایشی (soft-delete با ممیزی) تا صفحه‌ی «حذف‌شده‌ها»ی ادمین
    هم داده داشته باشد

اجرا:
    python clear_and_reseed.py

اجرای مجدد امن است: هر بار قبل از ساخت داده‌ی تازه، داده‌ی قبلیِ همین
۴ کاربر آزمایشی پاک می‌شود.
"""
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_

from app.database.database import SessionLocal
from app.models.user import User
from app.models.lead import Lead
from app.models.task import Task
from app.models.activity import Activity
from app.models.product import Product
from app.models.sale_item import SaleItem
from app.models.lead_submission import LeadSubmission
from app.models.lead_deletion_audit import LeadDeletionAudit
from app.models.assignment_history import AssignmentHistory
from app.auth.hashing import hash_password

# اختیاری: اگر این مدل‌ها در پروژه‌ی شما وجود دارند و به لید/کاربر متصل‌اند،
# اسکریپت آن‌ها را هم پاک می‌کند تا خطای FK ندهد. اگر یکی از این ایمپورت‌ها
# در پروژه‌ی شما وجود ندارد یا اسم فایل/کلاس فرق دارد، همان بلوک try را
# با نام درست جایگزین کنید یا خط مربوطه را کامنت کنید.
try:
    from app.models.lead_escalation import LeadEscalation
except ImportError:
    LeadEscalation = None

try:
    from app.models.attachment import Attachment
except ImportError:
    Attachment = None

try:
    from app.models.notification import Notification
except ImportError:
    Notification = None

try:
    from app.models.audit_log import AuditLog
except ImportError:
    AuditLog = None


db = SessionLocal()

# ==================================================================
# بخش صفر — نشانه‌ی امن برای شناسایی داده‌ی آزمایشیِ قبلی
# ==================================================================
SEED_USER_MOBILES = [
    "09120000001",
    "09120000002",
    "09120000003",
    "09120000004",
]

seed_users = (
    db.query(User).filter(User.mobile.in_(SEED_USER_MOBILES)).all()
)
seed_user_ids = [u.id for u in seed_users]

if not seed_user_ids:
    print("ℹ️ کاربر آزمایشی قبلی پیدا نشد؛ پاک‌سازی رد شد و مستقیم می‌رویم سراغ ساخت.")
else:
    print(f"🔎 {len(seed_user_ids)} کاربر آزمایشی قبلی پیدا شد: {SEED_USER_MOBILES}")

# لیدهایی که owner یا creator‌شان یکی از کاربران آزمایشی است — این‌ها
# «داده‌ی آزمایشیِ ما» به‌حساب می‌آیند، صرف‌نظر از این‌که الان owner واقعی
# آن‌ها همان کاربر باشد یا بعداً به کس دیگری assign شده باشد.
seed_lead_ids = []
if seed_user_ids:
    seed_leads_query = db.query(Lead.id).filter(
        or_(
            Lead.owner_id.in_(seed_user_ids),
            Lead.created_by_id.in_(seed_user_ids),
        )
    )
    seed_lead_ids = [row[0] for row in seed_leads_query.all()]

print(f"🔎 {len(seed_lead_ids)} لید آزمایشی قبلی برای پاک‌سازی شناسایی شد.")

# نام‌های کاتالوگ رسمی — اینجا تعریف می‌شود چون بخش پاک‌سازی هم به آن نیاز دارد
PRODUCT_NAMES = [
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
]


# ==================================================================
# بخش یک — پاک‌سازی به ترتیب صحیح وابستگی (فرزندان قبل از والدین)
# ==================================================================
if seed_lead_ids:
    deleted_sale_items = (
        db.query(SaleItem)
        .filter(SaleItem.lead_id.in_(seed_lead_ids))
        .delete(synchronize_session=False)
    )
    deleted_activities = (
        db.query(Activity)
        .filter(Activity.lead_id.in_(seed_lead_ids))
        .delete(synchronize_session=False)
    )
    deleted_tasks = (
        db.query(Task)
        .filter(Task.lead_id.in_(seed_lead_ids))
        .delete(synchronize_session=False)
    )
    deleted_submissions = (
        db.query(LeadSubmission)
        .filter(LeadSubmission.lead_id.in_(seed_lead_ids))
        .delete(synchronize_session=False)
    )

    deleted_escalations = 0
    if LeadEscalation is not None:
        deleted_escalations = (
            db.query(LeadEscalation)
            .filter(LeadEscalation.lead_id.in_(seed_lead_ids))
            .delete(synchronize_session=False)
        )

    deleted_assignments = 0
    if AssignmentHistory is not None:
        deleted_assignments = (
            db.query(AssignmentHistory)
            .filter(AssignmentHistory.lead_id.in_(seed_lead_ids))
            .delete(synchronize_session=False)
        )

    deleted_attachments = 0
    if Attachment is not None:
        deleted_attachments = (
            db.query(Attachment)
            .filter(Attachment.lead_id.in_(seed_lead_ids))
            .delete(synchronize_session=False)
        )

    deleted_notifications = 0
    if Notification is not None:
        deleted_notifications = (
            db.query(Notification)
            .filter(Notification.lead_id.in_(seed_lead_ids))
            .delete(synchronize_session=False)
        )

    # ممیزی‌های حذف مربوط به این لیدها یا این کاربران (owner/deleted_by)
    deleted_deletion_audits = (
        db.query(LeadDeletionAudit)
        .filter(
            or_(
                LeadDeletionAudit.owner_id.in_(seed_user_ids),
                LeadDeletionAudit.deleted_by_id.in_(seed_user_ids),
            )
        )
        .delete(synchronize_session=False)
    )

    deleted_audit_logs = 0
    if AuditLog is not None:
        deleted_audit_logs = (
            db.query(AuditLog)
            .filter(AuditLog.user_id.in_(seed_user_ids))
            .delete(synchronize_session=False)
        )

    # حالا خود لیدها
    deleted_leads = (
        db.query(Lead)
        .filter(Lead.id.in_(seed_lead_ids))
        .delete(synchronize_session=False)
    )

    db.commit()

    print("🧹 پاک‌سازی انجام شد:")
    print(f"   - {deleted_sale_items} قلم فروش")
    print(f"   - {deleted_activities} فعالیت")
    print(f"   - {deleted_tasks} وظیفه")
    print(f"   - {deleted_submissions} ثبت تکراری")
    print(f"   - {deleted_escalations} ارجاع/تشدید")
    print(f"   - {deleted_assignments} تاریخچه‌ی assignment")
    print(f"   - {deleted_attachments} پیوست")
    print(f"   - {deleted_notifications} اعلان")
    print(f"   - {deleted_deletion_audits} ممیزی حذف")
    print(f"   - {deleted_audit_logs} رکورد audit log")
    print(f"   - {deleted_leads} لید")

# توجه: خود کاربران آزمایشی (سارا/علی/مریم/حسین) پاک نمی‌شوند — چون
# ممکن است دیگر منابع (Session، توکن‌های لاگین ذخیره‌شده در فرانت، و...)
# به id همین کاربرها وابسته باشند. فقط داده‌های لید/فروش‌شان بازسازی می‌شود.

# پاک‌سازی محصولات قبلی (بسته‌های نرم‌افزاری) — چون کاتالوگ کاملاً عوض می‌شود
# باگ قبلی: اینجا «همه‌ی» محصولات بی‌قیدوشرط پاک می‌شدند، در حالی که
# پاک‌سازی اقلام فروشِ بالا فقط اقلامِ لیدهای ۴ کاربر آزمایشی را حذف
# می‌کند. اگر seed_sales_and_products.py روی لیدهای سایر کاربران قلم
# فروش ساخته بود، DELETE FROM products با نقض کلید خارجی شکست می‌خورد
# و کل اسکریپت نیمه‌کاره می‌ماند.
# قرارداد امن اسکریپت: محصولاتِ ارجاع‌شده (دارای قلم فروش) هرگز پاک
# نمی‌شوند؛ فقط محصولات قدیمیِ بدون ارجاع حذف می‌گردند و کاتالوگ رسمی
# در بخش سه به‌صورت upsert ساخته می‌شود (بدون تضاد یکتایی نام).
_referenced_ids = {row[0] for row in db.query(SaleItem.product_id).distinct().all()}
_stale_q = db.query(Product).filter(~Product.name.in_(PRODUCT_NAMES))
if _referenced_ids:
    _stale_q = _stale_q.filter(~Product.id.in_(_referenced_ids))
deleted_products = _stale_q.delete(synchronize_session=False)
db.commit()
print(f"🧹 {deleted_products} محصول قدیمیِ بدون ارجاع پاک شد.")


# ==================================================================
# بخش دو — بازساخت / تضمین وجود کاربران آزمایشی
# ==================================================================
FAKE_USERS = [
    {"full_name": "سارا احمدی", "mobile": "09120000001", "role": "sales", "password": "Test1234!"},
    {"full_name": "علی رضایی", "mobile": "09120000002", "role": "sales", "password": "Test1234!"},
    {"full_name": "مریم کریمی", "mobile": "09120000003", "role": "sales", "password": "Test1234!"},
    {"full_name": "حسین منصوری", "mobile": "09120000004", "role": "manager", "password": "Test1234!"},
]

users = {}
for u in FAKE_USERS:
    existing = db.query(User).filter(User.mobile == u["mobile"]).first()
    if existing:
        users[u["mobile"]] = existing
        continue
    user = User(
        full_name=u["full_name"],
        mobile=u["mobile"],
        password=hash_password(u["password"]),
        role=u["role"],
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    db.flush()
    users[u["mobile"]] = user

db.commit()
print(f"✅ {len(users)} کاربر آزمایشی آماده شد (موجود یا تازه‌ساخته‌شده).")

user_list = list(users.values())
sales_users = [u for u in user_list if u.role == "sales"]

# ==================================================================
# بخش سه — کاتالوگ محصولات واقعیِ کسب‌وکار (هادی تهویه)
# ==================================================================


PRODUCT_BASE_PRICE = {
    "داکت اسپیلت": 85_000_000,
    "فن کوئل": 42_000_000,
    "چیلر": 320_000_000,
    "اسپیلت": 38_000_000,
    "کولر آبی": 14_000_000,
    "پکیج": 165_000_000,
    "رادیاتور": 9_500_000,
    "شیرآلات": 3_200_000,
    "هود سینک گاز": 6_800_000,
    "سایر": 2_500_000,
}

products = {}
for name in PRODUCT_NAMES:
    # upsert: محصول موجود (مثلاً ارجاع‌شده از اقلام فروش واقعی)
    # دوباره ساخته نمی‌شود تا UniqueConstraint(name) نقض نشود.
    product = db.query(Product).filter(Product.name == name).first()
    if product is None:
        product = Product(name=name, is_active=True)
        db.add(product)
        db.flush()
    else:
        product.is_active = True
    products[name] = product

db.commit()
print(f"✅ {len(products)} محصول واقعی (تجهیزات تهویه) ساخته شد.")
product_list = list(products.values())

# ==================================================================
# بخش چهار — لیدها روی ۹۰ روز گذشته، با نرخ فروش متفاوت برای هر کارشناس
# ==================================================================
STATUSES = [
    "new", "contacted", "no_answer", "negotiating", "waiting_customer",
    "catalog_sent", "price_sent", "proforma", "invoice", "final_factor",
    "closed_lost",
]

SOURCES = ["instagram", "telegram", "website", "referral", "phone_call", "bale"]

FIRST_NAMES = ["امیر", "زهرا", "محمد", "فاطمه", "رضا", "نگار", "کیانا", "پویا", "الناز", "بهنام", "سپیده", "آرش", "یاسمن", "کوروش", "نیلوفر", "بابک"]
LAST_NAMES = ["حسینی", "موسوی", "قاسمی", "نوروزی", "صادقی", "شریفی", "کاظمی", "یوسفی", "رستمی", "طاهری", "عباسی", "فلاحی"]

NEEDS = [
    "استعلام قیمت داکت اسپیلت برای دفتر کار",
    "مشاوره برای انتخاب چیلر ساختمان مسکونی",
    "درخواست نصب فن کوئل رستوران",
    "پیگیری سفارش قبلی پکیج حرارتی",
    "سوال درباره‌ی گارانتی اسپیلت",
    "درخواست نمایندگی فروش تجهیزات تهویه",
    "خرید عمده شیرآلات برای پروژه‌ی ساختمانی",
    "استعلام قیمت هود سینک گاز صنعتی",
    "درخواست دمو و بازدید حضوری از کارگاه",
    "پیگیری رضایت مشتری پس از نصب",
]

# نرخ فروش هدف برای هر کارشناس، تا نمودار «فروش به تفکیک کارشناس» و
# «نرخ تبدیل» واقعاً تفاوت معنادار نشان دهند (نه صرفاً نویز تصادفی)
SALES_PERFORMANCE = {
    # مضراب فروش بالاتر => نرخ final_factor بیشتر و مبلغ فروش بزرگ‌تر
    "09120000001": {"final_factor_weight": 20, "avg_deal_multiplier": 1.3},  # سارا - برترین فروشنده
    "09120000002": {"final_factor_weight": 14, "avg_deal_multiplier": 1.0},  # علی - متوسط
    "09120000003": {"final_factor_weight": 9, "avg_deal_multiplier": 0.8},   # مریم - ضعیف‌تر
}

now = datetime.now(timezone.utc)
created_leads = []

random.seed(2026)

NUM_LEADS = 220
NUM_DAYS = 90

for i in range(NUM_LEADS):
    name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
    mobile = f"091{random.randint(10000000, 99999999)}"

    owner = random.choice(sales_users) if sales_users else random.choice(user_list)
    perf = SALES_PERFORMANCE.get(owner.mobile, {"final_factor_weight": 12, "avg_deal_multiplier": 1.0})

    base_weights = [14, 12, 10, 10, 8, 8, 8, 6, 6, perf["final_factor_weight"], 6]
    status = random.choices(STATUSES, weights=base_weights, k=1)[0]

    days_ago = random.randint(0, NUM_DAYS)
    created_at = now - timedelta(days=days_ago, hours=random.randint(0, 23))

    is_closed = status in ("final_factor", "closed_lost")
    next_follow_up = None
    if not is_closed:
        offset_hours = random.randint(-72, 96)
        if random.random() < 0.75:
            next_follow_up = now + timedelta(hours=offset_hours)

    lead = Lead(
        customer_name=name,
        mobile=mobile,
        mobile_normalized=mobile,
        customer_name_normalized=name.replace(" ", ""),
        duplicate_count=0,
        source=random.choice(SOURCES),
        need=random.choice(NEEDS),
        status=status,
        created_by_id=owner.id,
        owner_id=owner.id,
        last_contact_at=created_at + timedelta(hours=random.randint(1, 48)) if status != "new" else None,
        next_follow_up=next_follow_up,
        created_at=created_at,
        updated_at=created_at,
        is_deleted=False,
        score=random.randint(0, 100),
    )

    if status == "closed_lost":
        lead.loss_reason = random.choice(["قیمت بالا", "عدم نیاز", "انتخاب رقیب", "عدم پاسخگویی مشتری"])

    db.add(lead)
    db.flush()
    created_leads.append((lead, perf))

db.commit()
print(f"✅ {len(created_leads)} لید آزمایشی روی {NUM_DAYS} روز گذشته ساخته شد.")

# ==================================================================
# بخش چهار و نیم — ارجاع بین کارشناسان (AssignmentHistory)
# ----------------------------------------------------------------
# نمودارهای «بیشترین ارجاع‌دهنده» و «ارجاع بین کاربران» مستقیماً از
# جدول assignment_history خوانده می‌شوند (ردیف‌هایی که
# assigned_by_id != assigned_to_id)، نه از یک فیلد روی خود Lead.
# پس برای حدود ۲۰٪ لیدها یک رکورد ارجاعِ واقعی می‌سازیم: یک کارشناس
# دیگر (نه owner فعلی) به‌عنوان ارجاع‌دهنده ثبت می‌شود.
# ==================================================================
referral_count = 0
if sales_users and len(sales_users) > 1:
    for lead, _perf in created_leads:
        if random.random() >= 0.20:
            continue
        other_sales = [u for u in sales_users if u.id != lead.owner_id]
        if not other_sales:
            continue
        referrer = random.choice(other_sales)
        assignment = AssignmentHistory(
            lead_id=lead.id,
            assigned_by_id=referrer.id,
            assigned_to_id=lead.owner_id,
            note="ارجاع آزمایشی برای تست نمودار ارجاع‌ها.",
            assigned_at=lead.created_at + timedelta(hours=random.randint(1, 24)),
        )
        db.add(assignment)
        referral_count += 1

    db.commit()

print(f"✅ {referral_count} ارجاع بین کارشناسان (AssignmentHistory) ساخته شد.")

# ==================================================================
# بخش پنج — اقلام فروش (SaleItem) برای لیدهای final_factor
# ==================================================================
items_created = 0
leads_with_sales = 0

for lead, perf in created_leads:
    if lead.status != "final_factor":
        continue

    num_items = random.randint(1, 3)
    chosen_products = random.sample(product_list, k=min(num_items, len(product_list)))

    total_for_lead = 0
    for product in chosen_products:
        base_price = PRODUCT_BASE_PRICE.get(product.name, 5_000_000)
        amount = int(base_price * perf["avg_deal_multiplier"] * random.uniform(0.75, 1.25))
        amount = round(amount, -4)

        sale_item = SaleItem(
            lead_id=lead.id,
            product_id=product.id,
            amount=amount,
            created_at=lead.created_at + timedelta(hours=random.randint(2, 96)),
        )
        db.add(sale_item)
        total_for_lead += amount
        items_created += 1

    lead.sale_amount = total_for_lead
    lead.sold_products = "، ".join(p.name for p in chosen_products)
    lead.invoice_number = f"INV-{2000 + leads_with_sales}"
    leads_with_sales += 1

db.commit()
print(f"✅ {items_created} قلم فروش برای {leads_with_sales} لید «فروش موفق» ساخته شد.")

# ==================================================================
# بخش شش — فعالیت‌ها (Activities)
# ==================================================================
ACTIVITY_TYPES = ["note", "call", "meeting", "message", "whatsapp", "sms", "email"]
OUTCOMES = ["interested", "no_answer", "wrong_number", "not_interested", "follow_up_later"]

activity_count = 0
for lead, _ in created_leads:
    if random.random() < 0.7:
        num_activities = random.randint(1, 4)
        for _ in range(num_activities):
            activity = Activity(
                lead_id=lead.id,
                user_id=lead.owner_id,
                activity_type=random.choice(ACTIVITY_TYPES),
                title="تماس با مشتری" if random.random() < 0.5 else "ثبت یادداشت پیگیری",
                description="پیگیری انجام شد و وضعیت مشتری بررسی گردید.",
                outcome=random.choice(OUTCOMES),
                created_at=lead.created_at + timedelta(hours=random.randint(1, 72)),
            )
            db.add(activity)
            activity_count += 1

db.commit()
print(f"✅ {activity_count} فعالیت ساخته شد.")

# ==================================================================
# بخش هفت — وظایف (Tasks): دیرکرد / امروز / آینده
# ==================================================================
TASK_TITLES = [
    "تماس پیگیری با مشتری",
    "ارسال کاتالوگ محصولات",
    "پیگیری پرداخت فاکتور",
    "هماهنگی بازدید حضوری از سایت",
    "ارسال پیش‌فاکتور",
    "پیگیری رضایت مشتری پس از نصب",
]

task_count = 0
all_lead_objs = [lead for lead, _ in created_leads]
sample_leads = random.sample(all_lead_objs, min(90, len(all_lead_objs)))

for lead in sample_leads:
    assignee_id = lead.owner_id
    bucket = random.choices(["overdue", "today", "future"], weights=[30, 30, 40], k=1)[0]
    if bucket == "overdue":
        due_at = now - timedelta(days=random.randint(1, 7), hours=random.randint(0, 12))
        status = "pending"
    elif bucket == "today":
        due_at = now.replace(hour=random.randint(9, 18), minute=random.choice([0, 15, 30, 45]))
        status = "pending"
    else:
        due_at = now + timedelta(days=random.randint(1, 14))
        status = random.choices(["pending", "done"], weights=[85, 15], k=1)[0]

    task = Task(
        lead_id=lead.id,
        created_by_id=assignee_id,
        assigned_to_id=assignee_id,
        title=random.choice(TASK_TITLES),
        description=f"مرتبط با لید «{lead.customer_name}»",
        due_at=due_at,
        status=status,
        completed_at=(now - timedelta(hours=random.randint(1, 48))) if status == "done" else None,
        is_deleted=False,
    )
    db.add(task)
    task_count += 1

db.commit()
print(f"✅ {task_count} وظیفه ساخته شد.")

# ==================================================================
# بخش هشت — چند ثبت تکراری (LeadSubmission) روی چند لید
# ==================================================================
submission_count = 0
leads_for_duplicates = random.sample(all_lead_objs, min(15, len(all_lead_objs)))

for lead in leads_for_duplicates:
    num_dupes = random.randint(1, 2)
    for idx in range(1, num_dupes + 1):
        submitter = random.choice(sales_users) if sales_users else lead.owner_id
        submission = LeadSubmission(
            lead_id=lead.id,
            submitted_by_id=submitter.id if hasattr(submitter, "id") else submitter,
            customer_name=lead.customer_name,
            customer_name_normalized=lead.customer_name_normalized,
            mobile=lead.mobile,
            mobile_normalized=lead.mobile_normalized,
            need=random.choice(NEEDS),
            source=random.choice(SOURCES),
            notes="ثبت مجدد آزمایشی برای تست صفحه‌ی سابقه‌ی ثبت‌های تکراری.",
            submission_index=idx,
            matched_by="mobile_and_name" if random.random() < 0.6 else "mobile",
            submitted_at=lead.created_at + timedelta(days=random.randint(1, 20)),
        )
        db.add(submission)
        submission_count += 1
    lead.duplicate_count = num_dupes

db.commit()
print(f"✅ {submission_count} ثبت تکراری برای {len(leads_for_duplicates)} لید ساخته شد.")

# ==================================================================
# بخش نه — چند حذف آزمایشی (تا صفحه‌ی «حذف‌شده‌ها»ی ادمین هم داده داشته باشد)
# ==================================================================
try:
    from app.crud.lead import delete_lead as crud_delete_lead

    leads_to_delete = random.sample(
        [lead for lead in all_lead_objs if lead.status not in ("final_factor",)],
        min(6, len(all_lead_objs)),
    )
    deleter = users.get("09120000004") or user_list[0]  # مدیر، به‌عنوان حذف‌کننده

    deleted_count = 0
    for lead in leads_to_delete:
        crud_delete_lead(db, lead, deleter)
        deleted_count += 1

    print(f"✅ {deleted_count} لید به‌صورت آزمایشی حذف (soft-delete) شد تا صفحه‌ی «حذف‌شده‌ها» هم داده داشته باشد.")
except Exception as exc:  # noqa: BLE001
    print(f"⚠️ ساخت حذف‌های آزمایشی رد شد (اختیاری بود): {exc}")

db.close()

print("\n🎉 پاک‌سازی و بازتولید داده‌ی آزمایشی با موفقیت انجام شد!")
print(f"   - {NUM_LEADS} لید روی {NUM_DAYS} روز گذشته")
print(f"   - {len(PRODUCT_NAMES)} محصول واقعی تجهیزات تهویه")
print("می‌توانید با هر یک از کاربران زیر وارد پنل شوید (رمز عبور همه: Test1234!):")
for u in FAKE_USERS:
    print(f"   - {u['full_name']} ({u['role']}): {u['mobile']}")
