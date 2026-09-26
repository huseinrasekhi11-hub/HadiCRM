"""add refresh_sessions (server-side refresh-token revocation/rotation)

نشست‌های توکن تمدید سمت سرور:
    پیش از این jti داخل refresh token هرگز ذخیره نمی‌شد؛ logout
    کلاینت‌ساید بود و توکن سرقت‌شده تا ۷ روز قابل replay بود. این
    جدول هر توکن تمدیدِ صادرشده را با خانواده‌ی چرخشِ آن ثبت می‌کند
    تا rotate/reuse-detection/revoke ممکن شود (app/services/auth_service.py).

Revision ID: c9f3a7d1e5b8
Revises: b7c4d9e1a203
Create Date: 2026-09-26 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c9f3a7d1e5b8'
down_revision: Union[str, Sequence[str], None] = 'b7c4d9e1a203'
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
    if 'refresh_sessions' not in _tables():
        op.create_table(
            'refresh_sessions',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('jti', sa.String(length=64), nullable=False),
            sa.Column(
                'user_id',
                sa.Integer(),
                sa.ForeignKey('users.id'),
                nullable=False,
            ),
            sa.Column('family_id', sa.String(length=64), nullable=False),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('revoked_reason', sa.String(length=50), nullable=True),
            sa.Column('replaced_by_jti', sa.String(length=64), nullable=True),
            sa.Column(
                'created_at',
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        )

    existing = _indexes('refresh_sessions')
    if 'ix_refresh_sessions_jti' not in existing:
        op.create_index(
            'ix_refresh_sessions_jti', 'refresh_sessions', ['jti'], unique=True
        )
    if 'ix_refresh_sessions_user_id' not in existing:
        op.create_index(
            'ix_refresh_sessions_user_id', 'refresh_sessions', ['user_id']
        )
    if 'ix_refresh_sessions_family_id' not in existing:
        op.create_index(
            'ix_refresh_sessions_family_id', 'refresh_sessions', ['family_id']
        )
    if 'ix_refresh_sessions_expires_at' not in existing:
        op.create_index(
            'ix_refresh_sessions_expires_at', 'refresh_sessions', ['expires_at']
        )


def downgrade() -> None:
    """Downgrade schema."""
    if 'refresh_sessions' in _tables():
        op.drop_table('refresh_sessions')
