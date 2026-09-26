"""
===========================================================
تمام مدل‌های دیتابیس
Alembic با import کردن این فایل
تمام جدول‌ها را شناسایی می‌کند.
===========================================================
"""
from app.models.user import User
from app.models.lead import Lead
from app.models.activity import Activity
from app.models.task import Task
from app.models.audit_log import AuditLog
from app.models.attachment import Attachment
from app.models.notification import Notification
from app.models.assignment_history import AssignmentHistory
from app.models.lead_escalation import LeadEscalation
from app.models.lead_submission import LeadSubmission
from app.models.lead_deletion_audit import LeadDeletionAudit
from app.models.product import Product
from app.models.sale_item import SaleItem
