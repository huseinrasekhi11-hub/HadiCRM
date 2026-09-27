"""
ساخت یک اکانت ادمین تازه و تمیز، مخصوص شما.
این اسکریپت هیچ اطلاعات کاربر دیگری را وارد نمی‌کند.
"""
import os

from app.database.database import SessionLocal
from app.models.user import User
from app.auth.hashing import hash_password

# ================================================
# این سه مقدار را قبل از اجرا با اطلاعات خودتان عوض کنید
# ================================================
FULL_NAME = os.environ.get("ADMIN_FULL_NAME", "System Administrator").strip()
MOBILE = os.environ.get("ADMIN_MOBILE", "").strip()
PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

if not MOBILE or not PASSWORD:
    raise SystemExit("ADMIN_MOBILE and ADMIN_PASSWORD must be explicitly set before creating an admin.")
# ================================================

db = SessionLocal()

from app.crud.user import get_user_by_mobile

existing = get_user_by_mobile(db, MOBILE)

if existing:
    print(f"⚠️ کاربری با موبایل {MOBILE} از قبل وجود دارد.")
else:
    user = User(
        full_name=FULL_NAME,
        mobile=MOBILE,
        password=hash_password(PASSWORD),
        role="admin",
        is_active=True,
        is_superuser=True,
    )
    db.add(user)
    db.commit()
    print(f"✅ اکانت ادمین «{FULL_NAME}» با موبایل {MOBILE} ساخته شد.")
    print("می‌توانید با همین شماره و رمز عبور وارد پنل شوید.")

db.close()