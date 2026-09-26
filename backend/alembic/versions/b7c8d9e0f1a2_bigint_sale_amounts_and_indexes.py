"""widen Rial amount columns to BIGINT and add hot-path indexes

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-09-26 00:00:00.000000

مبالغ فروش به ریال ذخیره می‌شوند. ستون‌های INTEGER (۳۲ بیتی) حداکثر
۲٬۱۴۷٬۴۸۳٬۶۴۷ ریال را می‌پذیرند؛ یعنی هر فروش بالاتر از حدود ۲٫۱ میلیارد
ریال (که برای تجهیزات تهویه کاملاً عادی است) با خطای
«integer out of range» رد می‌شد و اصلاً قابل ثبت نبود. این مهاجرت هر سه
ستون مبلغ را به BIGINT تبدیل می‌کند (تبدیل بدون از دست رفتن داده).

هم‌چنین ایندکس‌هایی که در مسیرهای پرتردد جا افتاده بودند اضافه می‌شوند:
  * leads.owner_id   — هر پرس‌وجوی کارشناس با این ستون فیلتر می‌شود
  * leads.status     — پایپ‌لاین/داشبورد
  * leads.created_at — ترتیب پیش‌فرض فهرست پرونده‌ها
  * audit_logs.created_at / notifications.created_at — ترتیب فیدها
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'leads', 'sale_amount',
        existing_type=sa.Integer(), type_=sa.BigInteger(), existing_nullable=True,
    )
    op.alter_column(
        'sale_line_items', 'amount',
        existing_type=sa.Integer(), type_=sa.BigInteger(), existing_nullable=False,
    )
    op.alter_column(
        'lead_deletion_audits', 'sale_amount',
        existing_type=sa.Integer(), type_=sa.BigInteger(), existing_nullable=True,
    )

    op.create_index('ix_leads_owner_id', 'leads', ['owner_id'])
    op.create_index('ix_leads_status', 'leads', ['status'])
    op.create_index('ix_leads_created_at', 'leads', ['created_at'])
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'])
    op.create_index('ix_notifications_created_at', 'notifications', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_notifications_created_at', table_name='notifications')
    op.drop_index('ix_audit_logs_created_at', table_name='audit_logs')
    op.drop_index('ix_leads_created_at', table_name='leads')
    op.drop_index('ix_leads_status', table_name='leads')
    op.drop_index('ix_leads_owner_id', table_name='leads')

    # توجه: اگر مقادیری بزرگ‌تر از ۳۲ بیت ثبت شده باشند، این downgrade شکست می‌خورد.
    op.alter_column(
        'lead_deletion_audits', 'sale_amount',
        existing_type=sa.BigInteger(), type_=sa.Integer(), existing_nullable=True,
    )
    op.alter_column(
        'sale_line_items', 'amount',
        existing_type=sa.BigInteger(), type_=sa.Integer(), existing_nullable=False,
    )
    op.alter_column(
        'leads', 'sale_amount',
        existing_type=sa.BigInteger(), type_=sa.Integer(), existing_nullable=True,
    )
