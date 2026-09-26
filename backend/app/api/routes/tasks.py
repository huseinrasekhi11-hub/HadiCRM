from fastapi import APIRouter
from fastapi import Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.crud.task import get_my_tasks
from app.database.database import get_db
from app.models.user import User
from app.schemas.task import TaskResponse

router = APIRouter(
    prefix="/tasks",
    tags=["Tasks"],
)


@router.get("/my", response_model=list[TaskResponse])
def read_my_tasks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_my_tasks(db, current_user)
