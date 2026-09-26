"""remove bale_chat_id from user (bot integration removed)

Revision ID: a1b2c3d4e5f6
Revises: f6a9b3c47d21
Create Date: 2026-09-19 00:00:00.000000

این استقرار به‌عنوان یک وب‌سایت/پنل مستقل اجرا می‌شود و هیچ اتصالی
به ربات بله ندارد؛ بنابراین ستون bale_chat_id (که فقط برای پیدا کردن
مقصد پیام‌های ربات استفاده می‌شد) دیگر لازم نیست.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f6a9b3c47d21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column('users', 'bale_chat_id')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('users', sa.Column('bale_chat_id', sa.String(length=50), nullable=True))
