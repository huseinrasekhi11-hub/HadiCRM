"""add lead duplicate support (normalized keys, duplicate counter, submissions table)

Revision ID: c9d2e7b4a1f8
Revises: a3f9c7d21b44
Create Date: 2026-08-01 00:00:00.000000
"""
import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c9d2e7b4a1f8'
down_revision: Union[str, Sequence[str], None] = 'a3f9c7d21b44'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------
# Self-contained normalization helpers (duplicated intentionally:
# migrations must not depend on application code).
# Mirrors app/core/text_normalization.py exactly.
# ---------------------------------------------------------------
_PERSIAN_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
_ARABIC_DIGIT_MAP = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_CHARACTER_MAP = str.maketrans(
    {
        "ي": "ی",
        "ك": "ک",
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ة": "ه",
        "ۀ": "ه",
        "ؤ": "و",
    }
)
_ZWNJ = "\u200c"


def _normalize_mobile(raw):
    if raw is None:
        return None
    text = str(raw)
    text = text.translate(_PERSIAN_DIGIT_MAP)
    text = text.translate(_ARABIC_DIGIT_MAP)
    digits = re.sub(r"\D", "", text)
    if not digits:
        return None
    if digits.startswith("0098"):
        digits = digits[4:]
    elif digits.startswith("98") and len(digits) in (12, 13):
        digits = digits[2:]
    if len(digits) == 10 and digits.startswith("9"):
        digits = "0" + digits
    return digits


def _normalize_name(raw):
    if raw is None:
        return None
    text = str(raw)
    text = text.translate(_PERSIAN_DIGIT_MAP)
    text = text.translate(_ARABIC_DIGIT_MAP)
    text = text.translate(_CHARACTER_MAP)
    text = text.replace(_ZWNJ, "")
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


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

    # === leads: normalized duplicate-detection keys + counter ===
    if 'mobile_normalized' not in _cols('leads'):
        op.add_column('leads', sa.Column('mobile_normalized', sa.String(length=30), nullable=True))
    if 'customer_name_normalized' not in _cols('leads'):
        op.add_column('leads', sa.Column('customer_name_normalized', sa.String(length=200), nullable=True))
    if 'duplicate_count' not in _cols('leads'):
        op.add_column(
            'leads',
            sa.Column('duplicate_count', sa.Integer(), nullable=False, server_default='0'),
        )
    if 'ix_leads_mobile_normalized' not in _idx('leads'):
        op.create_index(op.f('ix_leads_mobile_normalized'), 'leads', ['mobile_normalized'], unique=False)

    # === new table: repeated submissions attached to a lead ===
    if 'lead_submissions' not in _tables:
        op.create_table(
            'lead_submissions',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('lead_id', sa.Integer(), nullable=False),
            sa.Column('submitted_by_id', sa.Integer(), nullable=False),
            sa.Column('customer_name', sa.String(length=100), nullable=False),
            sa.Column('customer_name_normalized', sa.String(length=200), nullable=True),
            sa.Column('mobile', sa.String(length=20), nullable=False),
            sa.Column('mobile_normalized', sa.String(length=30), nullable=True),
            sa.Column('need', sa.String(length=500), nullable=True),
            sa.Column('source', sa.String(length=50), nullable=True),
            sa.Column('notes', sa.String(length=500), nullable=True),
            sa.Column('submission_index', sa.Integer(), nullable=False),
            sa.Column('matched_by', sa.String(length=30), nullable=False),
            sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ),
            sa.ForeignKeyConstraint(['submitted_by_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id'),
        )
    if 'ix_lead_submissions_lead_id' not in _idx('lead_submissions'):
        op.create_index(op.f('ix_lead_submissions_lead_id'), 'lead_submissions', ['lead_id'], unique=False)
    if 'ix_lead_submissions_submitted_by_id' not in _idx('lead_submissions'):
        op.create_index(
            op.f('ix_lead_submissions_submitted_by_id'),
            'lead_submissions',
            ['submitted_by_id'],
            unique=False,
        )
    if 'ix_lead_submissions_mobile_normalized' not in _idx('lead_submissions'):
        op.create_index(
            op.f('ix_lead_submissions_mobile_normalized'),
            'lead_submissions',
            ['mobile_normalized'],
            unique=False,
        )

    # === backfill normalized keys for existing leads ===
    conn = op.get_bind()
    leads_table = sa.table(
        'leads',
        sa.column('id', sa.Integer),
        sa.column('mobile', sa.String),
        sa.column('customer_name', sa.String),
        sa.column('mobile_normalized', sa.String),
        sa.column('customer_name_normalized', sa.String),
    )
    rows = conn.execute(
        sa.select(leads_table.c.id, leads_table.c.mobile, leads_table.c.customer_name)
    ).fetchall()
    for row in rows:
        conn.execute(
            leads_table.update()
            .where(leads_table.c.id == row.id)
            .values(
                mobile_normalized=_normalize_mobile(row.mobile),
                customer_name_normalized=_normalize_name(row.customer_name),
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_lead_submissions_mobile_normalized'), table_name='lead_submissions')
    op.drop_index(op.f('ix_lead_submissions_submitted_by_id'), table_name='lead_submissions')
    op.drop_index(op.f('ix_lead_submissions_lead_id'), table_name='lead_submissions')
    op.drop_table('lead_submissions')
    op.drop_index(op.f('ix_leads_mobile_normalized'), table_name='leads')
    op.drop_column('leads', 'duplicate_count')
    op.drop_column('leads', 'customer_name_normalized')
    op.drop_column('leads', 'mobile_normalized')
