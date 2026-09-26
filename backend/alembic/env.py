"""
===========================================================
HadiFlow

Alembic Environment

این فایل وظیفه اتصال Alembic به پروژه را برعهده دارد.

وظایف:

1- اتصال به دیتابیس
2- شناسایی مدل‌ها
3- ساخت Migration
4- بروزرسانی دیتابیس
===========================================================
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# ----------------------------------------------------------
# تنظیمات Alembic
# ----------------------------------------------------------

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ----------------------------------------------------------
# معرفی Base پروژه
# ----------------------------------------------------------

from app.database.base import Base

# ----------------------------------------------------------
# Import تمام مدل‌ها
# ----------------------------------------------------------

import app.models

target_metadata = Base.metadata

# ----------------------------------------------------------
# آدرس دیتابیس از تنظیمات برنامه (.env) خوانده می‌شود.
#
# پیش از این alembic.ini یک آدرس هاردکدشده داشت که با هیچ‌کدام از
# محیط‌های واقعی (docker-compose و ...) هم‌خوانی نداشت و مهاجرت‌ها
# عملاً قابل اجرا نبودند.
# ----------------------------------------------------------
from app.config.settings import settings  # noqa: E402

config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)


# ----------------------------------------------------------
# اجرای Migration بدون اتصال
# ----------------------------------------------------------

def run_migrations_offline():

    url = config.get_main_option("sqlalchemy.url")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# ----------------------------------------------------------
# اجرای Migration با اتصال واقعی
# ----------------------------------------------------------

def run_migrations_online():

    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():

    run_migrations_offline()

else:

    run_migrations_online()
