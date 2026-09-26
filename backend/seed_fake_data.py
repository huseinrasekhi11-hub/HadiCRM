"""
اسکریپت تولید داده‌ی آزمایشی (Fake Data) برای تست داشبورد و پنل.

این اسکریپت چند کاربر (فروشنده/مدیر)، چندین لید در مراحل مختلف پایپ‌لاین،
چند وظیفه (Task) و چند اقدام (Activity) با تاریخ‌های واقع‌گرایانه می‌سازد
تا داشبورد، لیست لیدها، صفحه‌ی وظایف و نمودارها همگی داده برای نمایش داشته باشند.

این اسکریپت را می‌توانید چند بار اجرا کنید؛ هر بار رکوردهای تازه اضافه می‌شوند
(کاربران تکراری به خاطر شماره موبایل یکتا، اضافه نخواهند شد).

اجرا:
    python seed_fake_data.py
"""
import random
from datetime import datetime, timedelta, timezone

from app.database.database import SessionLocal
from app.models.user import User
from app.models.lead import Lead
from app.models.task import Task
from app.models.activity import Activity
from app.auth.hashing import hash_password

db = SessionLocal()

# ----------------------------------------------------------------
# 1) کاربران آزمایشی (فروشنده‌ها و یک مدیر)
# ----------------------------------------------------------------
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
print(f"✅ {len(users)} کاربر آماده شد (موجود یا تازه‌ساخته‌شده).")

user_list = list(users.values())

# ----------------------------------------------------------------
# 2) لیدهای آزمایشی در مراحل مختلف پایپ‌لاین
# ----------------------------------------------------------------
STATUSES = [
    "new", "contacted", "no_answer", "negotiating", "waiting_customer",
    "catalog_sent", "price_sent", "proforma", "invoice", "final_factor",
    "closed_lost",
]

SOURCES = ["instagram", "telegram", "website", "referral", "phone_call", "bale"]

FIRST_NAMES = ["امیر", "زهرا", "محمد", "فاطمه", "رضا", "نگار", "کیانا", "پویا", "الناز", "بهنام", "سپیده", "آرش"]
LAST_NAMES = ["حسینی", "موسوی", "قاسمی", "نوروزی", "صادقی", "شریفی", "کاظمی", "یوسفی", "رستمی", "طاهری"]

NEEDS = [
    "خرید بسته‌ی نرم‌افزار حسابداری",
    "مشاوره برای راه‌اندازی فروشگاه آنلاین",
    "استعلام قیمت محصولات صنعتی",
    "درخواست دمو رایگان",
    "پیگیری سفارش قبلی",
    "سوال درباره‌ی گارانتی محصول",
    "درخواست نمایندگی فروش",
    "خرید عمده برای دفتر شرکت",
]

now = datetime.now(timezone.utc)
created_leads = []

random.seed(42)  # نتایج قابل تکرار برای دیباگ راحت‌تر

NUM_LEADS = 60

for i in range(NUM_LEADS):
    name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
    mobile = f"091{random.randint(10000000, 99999999)}"
    status = random.choices(
        STATUSES,
        weights=[14, 12, 10, 10, 8, 8, 8, 6, 6, 12, 6],  # جدیدها و فروش‌های موفق کمی بیشتر
        k=1,
    )[0]
    owner = random.choice(user_list)
    days_ago = random.randint(0, 45)
    created_at = now - timedelta(days=days_ago, hours=random.randint(0, 23))

    is_closed = status in ("final_factor", "closed_lost")
    next_follow_up = None
    if not is_closed:
        # حدود نیمی از لیدهای باز یک پیگیری آینده دارند (بعضی گذشته = دیرکرد، بعضی آینده)
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

    if status == "final_factor":
        lead.sale_amount = random.choice([1500000, 2500000, 4200000, 7800000, 12000000, 25000000])
        lead.sold_products = random.choice(["بسته‌ی پایه", "بسته‌ی حرفه‌ای", "بسته‌ی سازمانی"])
        lead.invoice_number = f"INV-{1000 + i}"
    elif status == "closed_lost":
        lead.loss_reason = random.choice(["قیمت بالا", "عدم نیاز", "انتخاب رقیب", "عدم پاسخگویی مشتری"])

    db.add(lead)
    db.flush()
    created_leads.append(lead)

db.commit()
print(f"✅ {len(created_leads)} لید آزمایشی ساخته شد.")

# ----------------------------------------------------------------
# 3) اقدامات (Activities) برای چند لید — برای پر شدن تاریخچه
# ----------------------------------------------------------------
ACTIVITY_TYPES = ["note", "call", "meeting", "message", "whatsapp", "sms", "email"]
OUTCOMES = ["interested", "no_answer", "wrong_number", "not_interested", "follow_up_later"]

activity_count = 0
for lead in created_leads:
    if random.random() < 0.7:  # اکثر لیدها حداقل یک اقدام دارند
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
print(f"✅ {activity_count} اقدام (Activity) ساخته شد.")

# ----------------------------------------------------------------
# 4) وظایف (Tasks) — شامل امروز، دیرکرد و آینده، برای تست صفحه‌ی وظایف
# ----------------------------------------------------------------
TASK_TITLES = [
    "تماس پیگیری با مشتری",
    "ارسال کاتالوگ محصولات",
    "پیگیری پرداخت فاکتور",
    "هماهنگی جلسه‌ی حضوری",
    "ارسال پیش‌فاکتور",
    "پیگیری رضایت مشتری پس از فروش",
]

task_count = 0
sample_leads = random.sample(created_leads, min(35, len(created_leads)))

for lead in sample_leads:
    assignee = random.choice(user_list)
    # توزیع: دیرکرد / امروز / آینده
    bucket = random.choices(["overdue", "today", "future"], weights=[30, 30, 40], k=1)[0]
    if bucket == "overdue":
        due_at = now - timedelta(days=random.randint(1, 5), hours=random.randint(0, 12))
        status = "pending"
    elif bucket == "today":
        due_at = now.replace(hour=random.randint(9, 18), minute=random.choice([0, 15, 30, 45]))
        status = "pending"
    else:
        due_at = now + timedelta(days=random.randint(1, 10))
        status = random.choices(["pending", "done"], weights=[85, 15], k=1)[0]

    task = Task(
        lead_id=lead.id,
        created_by_id=assignee.id,
        assigned_to_id=assignee.id,
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
print(f"✅ {task_count} وظیفه (Task) ساخته شد.")

db.close()

print("\n🎉 داده‌های آزمایشی با موفقیت ساخته شدند!")
print("می‌توانید با هر یک از کاربران زیر وارد پنل شوید (رمز عبور همه: Test1234!):")
for u in FAKE_USERS:
    print(f"   - {u['full_name']} ({u['role']}): {u['mobile']}")
