"""
===========================================================
مدل کاربران (User Model)

هر شخصی که وارد HadiFlow شود، یک رکورد در این جدول خواهد داشت.

نمونه‌ها:
- مدیرعامل
- فروشنده
- حسابدار
- انباردار
- تکنسین
===========================================================
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class User(Base):
    """
    مدل کاربران سیستم
    """

    __tablename__ = "users"

    # ----------------------------------------------------
    # شناسه اصلی
    # ----------------------------------------------------
    id: Mapped[int] = mapped_column(primary_key=True)

    # ----------------------------------------------------
    # نام کامل
    # ----------------------------------------------------
    full_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # ----------------------------------------------------
    # شماره موبایل
    # ----------------------------------------------------
    mobile: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
    )

    # ----------------------------------------------------
    # شماره موبایل canonical (هویت یکتای نرمال‌شده)
    #
    # «09121111111»، «+989121111111» و «۰۹۱۲۱۱۱۱۱۱۱» یک شماره‌اند؛
    # پیش از این هر کدام هویت جدا بودند و لاگین با برابریِ دقیقِ
    # رشته‌ی خام انجام می‌شد (کاربر با فرمتِ متفاوت قفل می‌شد).
    # این ستون همیشه از روی mobile محاسبه می‌شود (event listener
    # پایین) و جست‌وجوی هویت/لاگین اول از آن استفاده می‌کند.
    # NULL فقط برای داده‌ی قدیمیِ متناقض (دو حساب با شماره‌ی معادل)
    # مجاز است؛ ایندکس یکتا چند NULL را در PostgreSQL تحمل می‌کند.
    # ----------------------------------------------------
    mobile_normalized: Mapped[str | None] = mapped_column(
        String(20),
        unique=True,
        nullable=True,
    )

    # ----------------------------------------------------
    # رمز عبور (Hash)
    # ----------------------------------------------------
    password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # ----------------------------------------------------
    # نقش کاربر
    # ----------------------------------------------------
    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    # ----------------------------------------------------
    # وضعیت فعال بودن
    # ----------------------------------------------------
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # ----------------------------------------------------
    # مدیر سیستم
    # ----------------------------------------------------
    is_superuser: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # ----------------------------------------------------
    # زمان ایجاد
    # ----------------------------------------------------
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ----------------------------------------------------
    # زمان آخرین بروزرسانی
    # ----------------------------------------------------
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ----------------------------------------------------
    # آخرین ورود
    # ----------------------------------------------------
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Incremented whenever existing access tokens must be invalidated
    # immediately (password change/reset or account deactivation).
    session_version: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        server_default="0",
    )
    # فیلدهای فاز ۱۱ و ۱۲ (مدیریت پرسنل و دسترسی پویا)
    #
    # توجه: پیش از این همین‌جا دوباره «is_active = Column(...)» تعریف شده
    # بود که تعریف تایپ‌دار بالا را بی‌صدا بازنویسی می‌کرد و nullable=False
    # را از بین می‌برد. تعریف تکراری حذف شد؛ مرجع یگانه، همان ستون بالاست.
    permissions = Column(JSON, default=list) # ذخیره دسترسی‌های نقطه‌ای به صورت آرایه


# ==========================================================
# همگام‌سازی خودکار mobile_normalized
# هر مسیر ساخت/به‌روزرسانی User (CRUD، اسکریپت‌های seed، تست‌ها)
# بدون نیاز به تغییر کد، ستون canonical را پر نگه می‌دارد.
# ==========================================================
from sqlalchemy import event  # noqa: E402

from app.core.text_normalization import normalize_mobile  # noqa: E402


@event.listens_for(User, "before_insert")
@event.listens_for(User, "before_update")
def _sync_user_mobile_normalized(_mapper, _connection, target: User) -> None:
    if target.mobile:
        target.mobile_normalized = normalize_mobile(target.mobile)