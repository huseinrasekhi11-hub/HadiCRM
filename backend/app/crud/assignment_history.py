from sqlalchemy.orm import Session

from app.models.assignment_history import AssignmentHistory
from app.models.lead import Lead
from app.models.user import User


def log_assignment(
    db: Session,
    lead: Lead,
    assigned_by: User,
    assigned_to: User,
    note: str | None = None,
    commit: bool = True,
):
    record = AssignmentHistory(
        lead_id=lead.id,
        assigned_by_id=assigned_by.id,
        assigned_to_id=assigned_to.id,
        note=note,
    )
    db.add(record)

    if commit:
        db.commit()
        db.refresh(record)

    return record


def get_lead_assignment_history(db: Session, lead: Lead):
    return (
        db.query(AssignmentHistory)
        .filter(AssignmentHistory.lead_id == lead.id)
        .order_by(AssignmentHistory.assigned_at.desc())
        .all()
    )
