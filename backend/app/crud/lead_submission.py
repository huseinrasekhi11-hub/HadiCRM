"""
CRUD برای تاریخچه‌ی ثبت‌های تکراری لید (Lead Submissions)
"""
from sqlalchemy.orm import Session

from app.models.lead import Lead
from app.models.lead_submission import LeadSubmission
from app.models.user import User


def get_lead_submissions(db: Session, lead: Lead) -> list[LeadSubmission]:
    """
    تمام ثبت‌های تکراری یک پرونده، از جدیدترین به قدیمی‌ترین.
    """
    return (
        db.query(LeadSubmission)
        .filter(LeadSubmission.lead_id == lead.id)
        .order_by(
            LeadSubmission.submitted_at.desc(),
            LeadSubmission.id.desc(),
        )
        .all()
    )


def get_lead_submissions_with_submitter(db: Session, lead: Lead) -> list[dict]:
    """
    ثبت‌های تکراری به همراه نام کامل ثبت‌کننده (برای نمایش در فرانت‌اند،
    بدون نیاز به درخواست جداگانه برای هر رکورد).
    """
    rows = (
        db.query(LeadSubmission, User.full_name)
        .outerjoin(User, LeadSubmission.submitted_by_id == User.id)
        .filter(LeadSubmission.lead_id == lead.id)
        .order_by(
            LeadSubmission.submitted_at.desc(),
            LeadSubmission.id.desc(),
        )
        .all()
    )

    return [
        {
            "id": submission.id,
            "lead_id": submission.lead_id,
            "submitted_by_id": submission.submitted_by_id,
            "submitted_by_full_name": full_name,
            "customer_name": submission.customer_name,
            "mobile": submission.mobile,
            "mobile_normalized": submission.mobile_normalized,
            "need": submission.need,
            "source": submission.source,
            "notes": submission.notes,
            "submission_index": submission.submission_index,
            "matched_by": submission.matched_by,
            "submitted_at": submission.submitted_at,
        }
        for submission, full_name in rows
    ]
