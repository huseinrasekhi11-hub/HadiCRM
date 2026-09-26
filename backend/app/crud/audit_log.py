from sqlalchemy.orm import Session
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
    except Exception as e:
        db.rollback()
        print(f"Error saving audit log: {e}")
        return None
def get_audit_logs(db: Session, skip: int = 0, limit: int = 100):
    # استخراج لاگ‌ها از جدیدترین به قدیمی‌ترین
    return db.query(AuditLog).order_by(AuditLog.created_at.desc()).offset(skip).limit(limit).all()
