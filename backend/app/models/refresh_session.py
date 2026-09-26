"""
===========================================================
مدل نشستِ توکن تمدید (Refresh Session)
-----------------------------------------------------------
پیش از این refresh tokenها فقط یک jti امضاشده داخل JWT داشتند که
هرگز سمت سرور ذخیره نمی‌شد؛ یعنی:
  * توکن تمدیدِ سرقت‌شده تا ۷ روز قابل replay بود،
  * logout صرفاً کلاینت‌ساید بود و هیچ چیزی را باطل نمی‌کرد،
  * غیرفعال‌سازی کاربر، نشست‌های در جریان او را cut نمی‌کرد.

حالا هر refresh token یک رکورد نشست دارد:
  * jti: شناسه‌ی یکتای خود توکن (کلید lookup)
  * family_id: زنجیره‌ی چرخش توکن‌ها — هر لاگین یک خانواده‌ی جدید
    می‌سازد و هر چرخش، عضو جدیدی در همان خانواده است. استفاده‌ی
    مجدد از یک توکنِ مصرف‌شده (نشانه‌ی سرقت) کل خانواده را باطل
    می‌کند، چون یا دزد توکن جدید را دارد یا کاربر واقعی — در هر
    حال هر دو از کار می‌افتند و کاربر با لاگین مجدد بازیابی می‌کند.
  * revoked_at / revoked_reason / replaced_by_jti: وضعیت ابطال و
    ردیابی چرخش.
  * expires_at: انقضای سمت سرور، مستقل از ادعای exp داخل JWT —
    حتی اگر توکنِ امضاشده هنوز معتبر به‌نظر برسد، نشستِ منقضی/
    باطل‌شده قابل استفاده نیست.
===========================================================
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base

# دلایل ابطال (برای ممیزی/دیباگ)
REVOKE_REASON_ROTATED = "rotated"          # چرخش عادی: توکن جدید جایگزین شد
REVOKE_REASON_LOGOUT = "logout"            # کاربر خروج زد
REVOKE_REASON_REUSE = "reuse_detected"     # replay یک توکن مصرف‌شده → کل خانواده باطل
REVOKE_REASON_USER_DISABLED = "user_disabled"  # حساب غیرفعال/حذف شد
REVOKE_REASON_PASSWORD_CHANGE = "password_change"


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)

    jti: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    family_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    revoked_reason: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    replaced_by_jti: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None
