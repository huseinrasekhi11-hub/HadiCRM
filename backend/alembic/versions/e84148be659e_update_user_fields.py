"""update user fields

Revision ID: e84148be659e
Revises: 6ea849d71db2
Create Date: 2026-07-04 20:30:02.123459

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e84148be659e'
down_revision: Union[str, Sequence[str], None] = '6ea849d71db2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_superuser",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    op.add_column(
        "users",
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.add_column(
        "users",
        sa.Column(
            "last_login",
            sa.DateTime(),
            nullable=True,
        ),
    )
    # ### end Alembic commands ###


def downgrade() -> None:

    op.drop_column("users", "last_login")
    op.drop_column("users", "updated_at")
    op.drop_column("users", "created_at")
    op.drop_column("users", "is_superuser")
    op.drop_column("users", "is_active")
