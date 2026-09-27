"""add login_rate_events (shared login brute-force budget)

محدودسازِ نرخ ورود پیش از این فقط در حافظه‌ی هر فرایند بود؛ با چند worker
یا چند replica، هر کدام بودجه‌ی مستقل داشتند و سقفِ مؤثرِ حدسِ رمز به
تعداد نمونه‌ها ضرب می‌شد. این جدول شمارنده را به دیتابیسِ مشترک منتقل
می‌کند (app/core/rate_limit.py → DatabaseRateLimiter).

Revision ID: e3f1c9b7d4a2
Revises: d2e6b4a8c1f5
Create Date: 2026-09-27 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e3f1c9b7d4a2'
down_revision: Union[str, Sequence[str], None] = 'd2e6b4a8c1f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return set(inspector.get_table_names())


def _indexes(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {i["name"] for i in inspector.get_indexes(table_name)}


def upgrade() -> None:
    """Upgrade schema."""
    if 'login_rate_events' not in _tables():
        op.create_table(
            'login_rate_events',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('event_key', sa.String(length=255), nullable=False),
            sa.Column(
                'created_at',
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

    existing = _indexes('login_rate_events')
    if 'ix_login_rate_events_event_key' not in existing:
        op.create_index(
            'ix_login_rate_events_event_key', 'login_rate_events', ['event_key']
        )
    if 'ix_login_rate_events_created_at' not in existing:
        op.create_index(
            'ix_login_rate_events_created_at', 'login_rate_events', ['created_at']
        )


def downgrade() -> None:
    """Downgrade schema."""
    if 'login_rate_events' in _tables():
        op.drop_table('login_rate_events')
