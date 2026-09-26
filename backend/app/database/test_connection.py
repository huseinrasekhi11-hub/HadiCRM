"""
===========================================================
تست اتصال PostgreSQL

این فایل فقط برای اطمینان از اتصال
برنامه به دیتابیس است.

در نسخه نهایی پروژه حذف خواهد شد.
===========================================================
"""

from sqlalchemy import text

from app.database.database import engine


try:
    with engine.connect() as connection:

        result = connection.execute(text("SELECT version();"))

        print("Database connection established.")

        print(result.fetchone()[0])

except Exception as error:

    print("Database connection failed.")

    print(error)
