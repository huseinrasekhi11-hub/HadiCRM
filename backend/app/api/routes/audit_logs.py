from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.constants.roles import Roles
from app.database.database import get_db
from app.models.user import User
from app.crud.audit_log import get_audit_logs

router = APIRouter(
    prefix="/audit-logs",
    tags=["Audit Logs"],
)

@router.get("/")
def read_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # فقط مدیرعامل و ادمین حق دیدن لاگ‌های سیستم را دارند
    if current_user.role not in (Roles.ADMIN, Roles.CEO):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only Admins and CEOs can view audit logs."
        )
    
    # Pagination exposed explicitly; the CRUD already defaults to 100.
    return get_audit_logs(db, skip=skip, limit=limit)
