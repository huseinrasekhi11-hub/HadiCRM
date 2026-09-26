#!/usr/bin/env bash
# ===========================================================
# HadiFlow — Render start command
#
# جایگزینِ فرمان قدیمی:
#   python -m app.scripts.create_tables && python -m app.scripts.seed_admin \
#     && python clear_and_reseed.py && uvicorn ...
#
# چرا؟ create_tables از Base.metadata.create_all استفاده می‌کند که
# «فقط جدولِ نبود را می‌سازد» و هرگز ستونِ جدید به جدولِ موجود اضافه
# نمی‌کند. بعد از مهاجرت‌های b7c4d9e1a203 (follow_up_notified)،
# c9f3a7d1e5b8 (refresh_sessions) و d2e6b4a8c1f5 (mobile_normalized)
# دیتابیسِ قدیمی فاقد این ستون‌ها می‌ماند و اولین کوئری ORM با
# «column ... does not exist» کل استقرار را با exit 1 می‌خواباند.
#
# مسیر درست: Alembic. ولی دیتابیسی که با create_all بالا آمده جدولِ
# alembic_version ندارد و «upgrade head» از صفر، روی جدول‌های موجود
# می‌ترکد. بنابراین اگر alembic_version وجود نداشت، اسکیمای فعلی را
# روی آخرین بازنگریِ پیش از این مهاجرت‌ها (b7c8d9e0f1a2) «stamp»
# می‌کنیم — سه مهاجرتِ جدید کاملاً idempotent و guard‌دار هستند، پس
# فقط آنچه واقعاً نبود اضافه می‌شود و داده‌ی موجود دست‌نخورده می‌ماند.
#
# در Render:  Start Command = bash render_start.sh
# ===========================================================
set -euo pipefail

# ۱) دیتابیسِ create_all-ساخته را یک‌بار stamp می‌کنیم (فقط اگر
#    alembic_version اصلاً وجود نداشته باشد).
probe="$(
  python - <<'PY'
from sqlalchemy import inspect
from app.database.database import engine
print("yes" if "alembic_version" in inspect(engine).get_table_names() else "no")
PY
)" || {
  echo "==> FATAL: database probe failed. Is DATABASE_URL set and the database reachable?" >&2
  exit 1
}
if [ "$probe" = "no" ]; then
  echo "==> No alembic_version table found (legacy create_all database)."
  echo "==> Stamping schema at b7c8d9e0f1a2 before upgrading."
  alembic stamp b7c8d9e0f1a2
fi

# ۲) اعمال مهاجرت‌ها (در دفعات بعد فقط مهاجرت‌های تازه اجرا می‌شوند)
echo "==> Applying database migrations"
alembic upgrade head

# ۳) ساخت ادمین (اگر وجود نداشته باشد)
echo "==> Seeding admin user"
python -m app.scripts.seed_admin

# ۴) داده‌ی دمو — مثل فرمان قبلی، هر بار بازنشانی می‌شود. وقتی داده‌ی
#    واقعی روی استقرار رفت، در محیط Render مقدار RESEED_DEMO_DATA=false
#    بگذارید تا این قدم حذف شود.
if [ "${RESEED_DEMO_DATA:-true}" = "true" ]; then
  echo "==> Reseeding demo data (set RESEED_DEMO_DATA=false to disable)"
  python clear_and_reseed.py
else
  echo "==> Demo reseed skipped (RESEED_DEMO_DATA=false)"
fi

# ۵) اجرای API
echo "==> Starting uvicorn on port ${PORT}"
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
