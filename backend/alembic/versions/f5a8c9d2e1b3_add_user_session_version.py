"""add user session_version for immediate access-token revocation

Revision ID: f5a8c9d2e1b3
Revises: e3f1c9b7d4a2
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f5a8c9d2e1b3"
down_revision: Union[str, Sequence[str], None] = "e3f1c9b7d4a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
    if "session_version" not in _columns("users"):
        op.add_column(
            "users",
            sa.Column(
                "session_version",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )


def downgrade() -> None:
    if "session_version" in _columns("users"):
        op.drop_column("users", "session_version")
