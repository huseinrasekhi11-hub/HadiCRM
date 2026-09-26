from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database.database import get_db
from app.crud.notification import (
    get_notifications,
    get_notification_feed,
    get_unread_count,
    mark_notification_read,
    mark_all_notifications_read,
)
from app.schemas.notification import NotificationResponse, NotificationSummary
from app.models.user import User

router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"],
)


@router.get("/")
def notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_notifications(
        db,
        current_user,
    )


@router.get("/feed", response_model=list[NotificationResponse])
def notification_feed(
    unread_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_notification_feed(db, current_user, unread_only=unread_only)


@router.get("/unread-count", response_model=NotificationSummary)
def notification_unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return {"unread_count": get_unread_count(db, current_user)}


@router.post("/{notification_id}/read", response_model=NotificationResponse)
def read_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notification = mark_notification_read(db, notification_id, current_user)
    if not notification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")
    return notification


@router.post("/read-all")
def read_all_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    mark_all_notifications_read(db, current_user)
    return {"status": "ok"}
