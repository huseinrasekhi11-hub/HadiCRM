"""
===========================================================
ساخت جدول‌ها در دیتابیس

این اسکریپت تمام مدل‌های تعریف‌شده در app/models را
بررسی کرده و در صورت نبودن، جدول متناظرشان را در
دیتابیس PostgreSQL می‌سازد.

نکته: این دستور جدول‌های موجود را تغییر نمی‌دهد،
فقط جدول‌های "جدید" را می‌سازد.
===========================================================
"""

from app.database.database import engine
from app.database.base import Base

# این ایمپورت باعث می‌شود همه مدل‌ها به Base شناسانده شوند
import app.models  # noqa

Base.metadata.create_all(bind=engine)

print("Tables created (or already existed).")
