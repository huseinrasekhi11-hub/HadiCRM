import os

from app.auth.hashing import hash_password
from app.constants.roles import Roles
from app.crud.user import get_user_by_mobile
from app.database.database import SessionLocal

# SECURITY: never fall back to a known production credential. The Render
# startup script calls this command automatically, so an omitted password
# must fail closed rather than creating an account with a published default.
ADMIN_MOBILE = os.environ.get("ADMIN_MOBILE", "").strip()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

if not ADMIN_MOBILE or not ADMIN_PASSWORD:
    raise SystemExit(
        "ADMIN_MOBILE and ADMIN_PASSWORD must be explicitly set before seeding the admin."
    )

db = SessionLocal()

try:
    # Canonical lookup makes the seeder idempotent across equivalent mobile
    # formats (e.g. +98912... versus 0912...) after mobile normalization.
    admin = get_user_by_mobile(db, ADMIN_MOBILE)

    if admin:
        print("Admin already exists.")

    else:
        admin = User(
            full_name="System Administrator",
            mobile=ADMIN_MOBILE,
            password=hash_password(ADMIN_PASSWORD),
            role=Roles.ADMIN,
        )

        db.add(admin)
        db.commit()

        print("Admin created successfully.")

finally:
    db.close()