"""add lead deletion audit (silent deletion snapshot table)

Revision ID: d4a7c1e85f23
Revises: c9d2e7b4a1f8
Create Date: 2026-08-02 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd4a7c1e85f23'
down_revision: Union[str, Sequence[str], None] = 'c9d2e7b4a1f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Idempotency guards (see b0c1d2e3f4a5): create_all-bootstrapped
    # databases already contain these objects; skip cleanly.
    _insp = sa.inspect(op.get_bind())
    _tables = set(_insp.get_table_names())

    def _cols(table):
        return {c["name"] for c in _insp.get_columns(table)} if table in _tables else set()

    def _idx(table):
        return {ix["name"] for ix in _insp.get_indexes(table)} if table in _tables else set()

    # === جدول ممیزی حذف لید ===
    # نکته‌ی طراحی: عمداً هیچ کلید خارجی (FK) به users/leads تعریف نمی‌شود
    # تا سند ممیزی حتی با حذف فیزیکی کاربر یا پاکسازی آینده‌ی لیدها
    # هرگز از بین نرود. نام‌ها به‌صورت اسنپ‌شات ذخیره می‌شوند.
    if 'lead_deletion_audits' not in _tables:
        op.create_table(
            'lead_deletion_audits',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('lead_id', sa.Integer(), nullable=False),
            sa.Column('customer_name', sa.String(length=100), nullable=False),
            sa.Column('mobile', sa.String(length=20), nullable=False),
            sa.Column('mobile_normalized', sa.String(length=30), nullable=True),
            sa.Column('source', sa.String(length=50), nullable=True),
            sa.Column('need', sa.String(length=500), nullable=True),
            sa.Column('previous_status', sa.String(length=50), nullable=False),
            sa.Column('loss_reason', sa.String(length=50), nullable=True),
            sa.Column('sale_amount', sa.Integer(), nullable=True),
            sa.Column('sold_products', sa.String(length=500), nullable=True),
            sa.Column('invoice_number', sa.String(length=50), nullable=True),
            sa.Column('owner_id', sa.Integer(), nullable=True),
            sa.Column('owner_full_name', sa.String(length=120), nullable=True),
            sa.Column('created_by_id', sa.Integer(), nullable=True),
            sa.Column('deleted_by_id', sa.Integer(), nullable=False),
            sa.Column('deleted_by_full_name', sa.String(length=120), nullable=True),
            sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('restored_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('restored_by_id', sa.Integer(), nullable=True),
            sa.Column('snapshot', sa.JSON(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )
    if 'ix_lead_deletion_audits_lead_id' not in _idx('lead_deletion_audits'):
        op.create_index(op.f('ix_lead_deletion_audits_lead_id'), 'lead_deletion_audits', ['lead_id'], unique=False)
    if 'ix_lead_deletion_audits_deleted_by_id' not in _idx('lead_deletion_audits'):
        op.create_index(op.f('ix_lead_deletion_audits_deleted_by_id'), 'lead_deletion_audits', ['deleted_by_id'], unique=False)
    if 'ix_lead_deletion_audits_deleted_at' not in _idx('lead_deletion_audits'):
        op.create_index(op.f('ix_lead_deletion_audits_deleted_at'), 'lead_deletion_audits', ['deleted_at'], unique=False)
    if 'ix_lead_deletion_audits_owner_id' not in _idx('lead_deletion_audits'):
        op.create_index(op.f('ix_lead_deletion_audits_owner_id'), 'lead_deletion_audits', ['owner_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_lead_deletion_audits_owner_id'), table_name='lead_deletion_audits')
    op.drop_index(op.f('ix_lead_deletion_audits_deleted_at'), table_name='lead_deletion_audits')
    op.drop_index(op.f('ix_lead_deletion_audits_deleted_by_id'), table_name='lead_deletion_audits')
    op.drop_index(op.f('ix_lead_deletion_audits_lead_id'), table_name='lead_deletion_audits')
    op.drop_table('lead_deletion_audits')
