"""
===========================================================
HadiFlow

مدیریت اتصال به دیتابیس

این فایل مسئول ایجاد Engine
و Session های دیتابیس است.

تمام Repository های پروژه
از همین Session استفاده خواهند کرد.
===========================================================
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import settings


# ----------------------------------------------------------
# ساخت Engine اتصال به PostgreSQL
# ----------------------------------------------------------
engine = create_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

# ----------------------------------------------------------
# ساخت Session دیتابیس
# ----------------------------------------------------------
SessionLocal = sessionmaker(
    autoflush=False,
    autocommit=False,
    bind=engine,
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
