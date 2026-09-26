"""
ثبت لاگ ممیزی (audit log).

سیاست فعلی: «non-fatal but monitored» — شکستِ ثبت audit log نباید
خودِ عملیات تجاری را rollback کند (مثلاً یک ارجاع موفق به‌خاطر خطای
نوشتن لاگ ۵۰۰ نشود)، اما شکست آن هرگز بی‌صدا نیست: با سطح EXCEPTION
و stack trace کامل در لاگ ساختاریافته ثبت می‌شود تا در مانیتورینگ
قابل شکار باشد. پیش از این خطا فقط با print خام بیرون می‌رفت (بدون
سطح، بدون stack trace، و در لاگ‌های ساختاریافته گم می‌شد) — یعنی
رکورد انطباق/امنیتی می‌توانست ناپدید شود و هیچ هشداری تولید نشود.
"""
from sqlalchemy.orm import Session

from app.core.logger import app_logger
from app.models.audit_log import AuditLog


def create_audit_log(db: Session, user_id: int, action: str, entity: str, entity_id: int, description: str):
    try:
        log = AuditLog(
            user_id=user_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            description=description
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log
    except Exception:
        db.rollback()
        # AUDIT-DURABILITY: شکستِ نوشتن لاگ ممیزی یک رویداد قابل‌هشدار
        # است، نه یک خطای بی‌اهمیت — با stack trace کامل ثبت می‌شود.
        app_logger.exception(
            f"AUDIT LOG WRITE FAILED (action={action}, entity={entity}, "
            f"entity_id={entity_id}, user_id={user_id}) — audit record lost."
        )
        return None


def get_audit_logs(db: Session, skip: int = 0, limit: int = 100):
    # استخراج لاگ‌ها از جدیدترین به قدیمی‌ترین
    return db.query(AuditLog).order_by(AuditLog.created_at.desc()).offset(skip).limit(limit).all()
