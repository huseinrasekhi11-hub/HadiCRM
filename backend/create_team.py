"""
اسکریپت یک‌بارمصرف برای ساخت اعضای تیم فروش.

اصلاح مهم: پیش از این این اسکریپت رمز عبور را با bcrypt خام
(bcrypt.hashpw) هش می‌کرد، در حالی که کل سامانه (app.auth.hashing)
از pwdlib با الگوریتم Argon2 استفاده می‌کند. نتیجه: کاربری که با این
اسکریپت ساخته می‌شد، هرگز نمی‌توانست وارد شود — verify_password یک
هش bcrypt خام را نمی‌شناسد و رد می‌کند. حالا از همان تابع رسمی
hash_password استفاده می‌شود تا با ورود واقعی سازگار باشد.

شماره‌های واقعی اعضای تیم عمداً حذف شدند؛ پیش از اجرا، فهرست را با
اطلاعات واقعی خودتان پر کنید. این فایل نباید با داده‌ی واقعی commit شود.
"""
from app.auth.hashing import hash_password
from app.database.database import SessionLocal
from app.models.user import User

# نمونه — پیش از اجرا با اطلاعات واقعی جایگزین کنید
TEAM_MEMBERS = [
    # {"full_name": "نام و نام خانوادگی", "mobile": "0912xxxxxxx", "role": "sales"},
]

DEFAULT_PASSWORD = "ChangeMe123!"


def create_team():
    if not TEAM_MEMBERS:
        print("⚠️ فهرست TEAM_MEMBERS خالی است. پیش از اجرا آن را پر کنید.")
        return

    db = SessionLocal()
    try:
        for member in TEAM_MEMBERS:
            existing_user = db.query(User).filter(User.mobile == member["mobile"]).first()
            if existing_user:
                print(f"⚠️ اکانت {member['full_name']} از قبل وجود دارد.")
                continue

            new_user = User(
                full_name=member["full_name"],
                mobile=member["mobile"],
                role=member["role"],
                password=hash_password(DEFAULT_PASSWORD),
                is_active=True,
            )
            db.add(new_user)
            print(f"✅ اکانت {member['full_name']} با موفقیت ساخته شد.")

        db.commit()
        print("🎉 ثبت‌نام تیم با موفقیت به پایان رسید!")
        print(f"💡 رمز عبور موقت همه: {DEFAULT_PASSWORD} — حتماً بعد از اولین ورود عوض شود.")
    except Exception as e:
        print(f"❌ خطا: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    create_team()
