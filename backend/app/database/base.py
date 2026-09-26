"""
===========================================================
Base Model

تمام مدل‌های پروژه از این کلاس
به ارث خواهند رسید.
===========================================================
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
