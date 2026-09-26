import os

from app.database.database import SessionLocal
from app.constants.roles import Roles
from app.models.user import User
from app.auth.hashing import hash_password

# Dev/demo defaults match the documented test-suite contract
# (tests/* expect 09120000000 / Admin123!). For any real deployment,
# set ADMIN_MOBILE / ADMIN_PASSWORD in the environment — and never ship
# the defaults to production.
ADMIN_MOBILE = os.environ.get("ADMIN_MOBILE", "09120000000")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin123!")

db = SessionLocal()

try:
    # آیا قبلاً ادمین وجود دارد؟
    admin = db.query(User).filter(User.mobile == ADMIN_MOBILE).first()

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
