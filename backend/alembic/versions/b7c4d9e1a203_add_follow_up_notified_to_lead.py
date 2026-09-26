"""add follow_up_notified to lead (Rule 4: follow-up-due reminder)

قانون ۴ (جدید) — یادآوری در لحظه‌ی سررسید پیگیری:
    تا پیش از این، هیچ نوتیفیکیشنی وقتی next_follow_up یک لید فرامی‌رسید
    ساخته نمی‌شد؛ کارشناس فقط در صورت باز کردن دستی صفحه‌ی «کارهای روزانه»
    متوجه آن می‌شد. این مهاجرت یک پرچمِ یک‌بارمصرف (مشابه sla_notified
    برای قانون ۱) اضافه می‌کند تا:
      1) job جدید بتواند لیدهایی را که سررسیدشان گذشته و هنوز پرچم
         نخورده‌اند پیدا کند،
      2) بعد از ارسال یادآوری، دوباره در اجرای بعدی job برای همان
         سررسید نوتیفیکیشن تکراری نسازد.
    وقتی next_follow_up دوباره (توسط کارشناس) تغییر کند، این پرچم باید
    False شود؛ این کار در لایه‌ی CRUD انجام می‌شود، نه در این مهاجرت.

Revision ID: b7c4d9e1a203
Revises: b7c8d9e0f1a2
Create Date: 2026-09-26 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7c4d9e1a203'
down_revision: Union[str, Sequence[str], None] = 'b7c8d9e0f1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _cols(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {c["name"] for c in inspector.get_columns(table_name)}


def upgrade() -> None:
    """Upgrade schema."""
    if 'follow_up_notified' not in _cols('leads'):
        op.add_column(
            'leads',
            sa.Column(
                'follow_up_notified',
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    """Downgrade schema."""
    if 'follow_up_notified' in _cols('leads'):
        op.drop_column('leads', 'follow_up_notified')
