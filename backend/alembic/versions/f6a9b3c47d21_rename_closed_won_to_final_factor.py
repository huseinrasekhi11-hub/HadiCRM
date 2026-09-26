"""rename success status closed_won -> final_factor

وضعیت رسمی «فروش موفق» به «final_factor» تغییر می‌کند؛ زیرا صدور
فاکتور/عامل نهایی به معنای تبدیل موفق لید است. چون جنس ستون
leads.status از نوع String(50) است (نه ENUM یا CHECK)، این مهاجرت
فقط یک تبدیل داده‌ی برگشت‌پذیر است و هیچ تغییر ساختاری ندارد.

Revision ID: f6a9b3c47d21
Revises: e5b8d2f6a934
Create Date: 2026-08-04 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f6a9b3c47d21'
down_revision: Union[str, Sequence[str], None] = 'e5b8d2f6a934'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade data: closed_won -> final_factor."""
    op.execute(
        sa.text(
            "UPDATE leads SET status = 'final_factor' WHERE status = 'closed_won'"
        )
    )


def downgrade() -> None:
    """Downgrade data: final_factor -> closed_won."""
    op.execute(
        sa.text(
            "UPDATE leads SET status = 'closed_won' WHERE status = 'final_factor'"
        )
    )
