from sqlalchemy.orm import Session
from app.models.attachment import Attachment
from app.models.lead import Lead
from app.models.user import User

def create_attachment(
    db: Session, 
    lead: Lead, 
    current_user: User, 
    file_name: str, 
    file_path: str
):
    attachment = Attachment(
        lead_id=lead.id,
        uploaded_by_id=current_user.id,
        file_name=file_name,
        file_path=file_path
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return attachment


def get_attachment_by_id(db: Session, attachment_id: int, lead_id: int):
    return (
        db.query(Attachment)
        .filter(Attachment.id == attachment_id, Attachment.lead_id == lead_id)
        .first()
    )


def get_lead_attachments(db: Session, lead_id: int):
    return (
        db.query(Attachment)
        .filter(Attachment.lead_id == lead_id)
        .order_by(Attachment.created_at.desc())
        .all()
    )
