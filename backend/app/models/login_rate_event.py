"""
===========================================================
رویدادهای ناموفقِ ورود (shared brute-force budget)
-----------------------------------------------------------
محدودسازِ نرخ ورود قبلاً فقط در حافظه‌ی هر فرایند بود؛ یعنی با
`uvicorn --workers 4` یا چند replica، هر فرایند بودجه‌ی مستقل خودش را
داشت و سقفِ مؤثرِ حدس رمز N برابر می‌شد (گزارش ممیزی: «MEDIUM — login
rate limiting is only per-process»).

این جدول همان شمارنده را به حالتِ «مشترک» می‌برد: هر تلاشِ ناموفق یک
ردیف با کلیدِ (IP + هویت) یا (IP) ثبت می‌کند و شمارش از دیتابیس خوانده
می‌شود — همان دیتابیسی که از قبل بین همه‌ی workerها/replicaها مشترک است.

چرا ردیف به‌جای ستونِ شمارنده؟ چون پنجره‌ی لغزنده (sliding window) با
ردیف‌های زمان‌دار دقیق است و به‌روزرسانیِ شرطی/قفلِ ردیف نیاز ندارد:
    DELETE قدیمی‌تر از پنجره → INSERT رویداد جدید → COUNT در پنجره
هزینه‌اش فقط روی تلاش‌های ناموفق است (که از قبل به‌خاطر Argon2 گران‌اند)
و حجمِ داده با پاک‌سازیِ خودکار محدود می‌ماند.
===========================================================
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class LoginRateEvent(Base):
    __tablename__ = "login_rate_events"

    id: Mapped[int] = mapped_column(primary_key=True)

    # کلید شمارنده: "ip:1.2.3.4" یا "acct:1.2.3.4|09120000000"
    event_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
