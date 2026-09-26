from sqlalchemy.orm import Session

from app.models.lead_escalation import LeadEscalation
from app.models.lead import Lead


def create_escalation(
    db: Session,
    lead: Lead,
    escalated_from_id: int,
    escalated_to_id: int,
    reason: str = "no_activity_3_days",
    commit: bool = True,
):
    record = LeadEscalation(
        lead_id=lead.id,
        escalated_from_id=escalated_from_id,
        escalated_to_id=escalated_to_id,
        reason=reason,
    )
    db.add(record)

    if commit:
        db.commit()
        db.refresh(record)

    return record


def get_lead_escalations(db: Session, lead: Lead):
    return (
        db.query(LeadEscalation)
        .filter(LeadEscalation.lead_id == lead.id)
        .order_by(LeadEscalation.created_at.desc())
        .all()
    )


def count_escalations_this_month(db: Session):
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    return (
        db.query(LeadEscalation)
        .filter(LeadEscalation.created_at >= month_start)
        .count()
    )
