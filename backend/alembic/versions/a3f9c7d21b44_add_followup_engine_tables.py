"""add follow-up engine tables (notifications, assignment history, escalations) and lead/activity extensions

Revision ID: a3f9c7d21b44
Revises: d8aa07eacfee
Create Date: 2026-07-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f9c7d21b44'
down_revision: Union[str, Sequence[str], None] = 'd8aa07eacfee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # Idempotency guards: databases bootstrapped with
    # Base.metadata.create_all already contain these objects; skip cleanly.
    _insp = sa.inspect(op.get_bind())
    _tables = set(_insp.get_table_names())

    def _cols(table):
        return {c["name"] for c in _insp.get_columns(table)} if table in _tables else set()

    def _idx(table):
        return {ix["name"] for ix in _insp.get_indexes(table)} if table in _tables else set()

    # === leads columns ===
    if 'last_assigned_at' not in _cols('leads'):
        op.add_column('leads', sa.Column('last_assigned_at', sa.DateTime(timezone=True), nullable=True))
    if 'sale_amount' not in _cols('leads'):
        op.add_column('leads', sa.Column('sale_amount', sa.Integer(), nullable=True))
    if 'sold_products' not in _cols('leads'):
        op.add_column('leads', sa.Column('sold_products', sa.String(length=500), nullable=True))
    if 'invoice_number' not in _cols('leads'):
        op.add_column('leads', sa.Column('invoice_number', sa.String(length=50), nullable=True))
    if 'resolution_notes' not in _cols('leads'):
        op.add_column('leads', sa.Column('resolution_notes', sa.String(length=500), nullable=True))

    # مقداردهی اولیه‌ی last_assigned_at برای رکوردهای موجود (بر اساس created_at)
    op.execute('UPDATE leads SET last_assigned_at = created_at WHERE last_assigned_at IS NULL')

    # === ستون‌های جدید روی activities ===
    if 'outcome' not in _cols('activities'):
        op.add_column('activities', sa.Column('outcome', sa.String(length=50), nullable=True))
    if 'next_follow_up' not in _cols('activities'):
        op.add_column('activities', sa.Column('next_follow_up', sa.DateTime(timezone=True), nullable=True))
    if 'no_followup_reason' not in _cols('activities'):
        op.add_column('activities', sa.Column('no_followup_reason', sa.String(length=300), nullable=True))

    # === جدول جدید: notifications ===
    if 'notifications' not in _tables:
        op.create_table(
            'notifications',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('lead_id', sa.Integer(), sa.ForeignKey('leads.id'), nullable=True),
            sa.Column('notification_type', sa.String(length=50), nullable=False),
            sa.Column('title', sa.String(length=150), nullable=False),
            sa.Column('message', sa.String(length=500), nullable=False),
            sa.Column('is_read', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        )
    if 'ix_notifications_user_id' not in _idx('notifications'):
        op.create_index('ix_notifications_user_id', 'notifications', ['user_id'])
    if 'ix_notifications_lead_id' not in _idx('notifications'):
        op.create_index('ix_notifications_lead_id', 'notifications', ['lead_id'])

    # === جدول جدید: assignment_history ===
    if 'assignment_history' not in _tables:
        op.create_table(
            'assignment_history',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('lead_id', sa.Integer(), sa.ForeignKey('leads.id'), nullable=False),
            sa.Column('assigned_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('assigned_to_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('note', sa.String(length=300), nullable=True),
            sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=False),
        )
    if 'ix_assignment_history_lead_id' not in _idx('assignment_history'):
        op.create_index('ix_assignment_history_lead_id', 'assignment_history', ['lead_id'])
    if 'ix_assignment_history_assigned_to_id' not in _idx('assignment_history'):
        op.create_index('ix_assignment_history_assigned_to_id', 'assignment_history', ['assigned_to_id'])

    # === جدول جدید: lead_escalations ===
    if 'lead_escalations' not in _tables:
        op.create_table(
            'lead_escalations',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('lead_id', sa.Integer(), sa.ForeignKey('leads.id'), nullable=False),
            sa.Column('escalated_from_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('escalated_to_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('reason', sa.String(length=50), nullable=False, server_default='no_activity_3_days'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        )
    if 'ix_lead_escalations_lead_id' not in _idx('lead_escalations'):
        op.create_index('ix_lead_escalations_lead_id', 'lead_escalations', ['lead_id'])
    if 'ix_lead_escalations_escalated_to_id' not in _idx('lead_escalations'):
        op.create_index('ix_lead_escalations_escalated_to_id', 'lead_escalations', ['escalated_to_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_lead_escalations_escalated_to_id', table_name='lead_escalations')
    op.drop_index('ix_lead_escalations_lead_id', table_name='lead_escalations')
    op.drop_table('lead_escalations')

    op.drop_index('ix_assignment_history_assigned_to_id', table_name='assignment_history')
    op.drop_index('ix_assignment_history_lead_id', table_name='assignment_history')
    op.drop_table('assignment_history')

    op.drop_index('ix_notifications_lead_id', table_name='notifications')
    op.drop_index('ix_notifications_user_id', table_name='notifications')
    op.drop_table('notifications')

    op.drop_column('activities', 'no_followup_reason')
    op.drop_column('activities', 'next_follow_up')
    op.drop_column('activities', 'outcome')

    op.drop_column('leads', 'resolution_notes')
    op.drop_column('leads', 'invoice_number')
    op.drop_column('leads', 'sold_products')
    op.drop_column('leads', 'sale_amount')
    op.drop_column('leads', 'last_assigned_at')
