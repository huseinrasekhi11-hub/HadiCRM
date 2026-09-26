"""
ساخت یک اکانت ادمین تازه و تمیز، مخصوص شما.
این اسکریپت هیچ اطلاعات کاربر دیگری را وارد نمی‌کند.
"""
from app.database.database import SessionLocal
from app.models.user import User
from app.auth.hashing import hash_password

# ================================================
# این سه مقدار را قبل از اجرا با اطلاعات خودتان عوض کنید
# ================================================
FULL_NAME = "System Administrator"
MOBILE = "09120000000"
PASSWORD = "ChangeMe123!"
# ================================================

db = SessionLocal()

existing = db.query(User).filter(User.mobile == MOBILE).first()

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
