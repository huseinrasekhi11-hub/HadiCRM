"""add users.mobile_normalized (canonical identity key)

هویت موبایل کاربر پیش از این با «برابریِ دقیقِ رشته‌ی خام» سنجیده
می‌شد: «09121111111» و «+989121111111» و «۰۹۱۲۱۱۱۱۱۱۱» سه هویت
جدا بودند؛ کاربری که شماره‌اش را با پیش‌شماره‌ی متفاوت وارد می‌کرد
دیگر نمی‌توانست لاگین کند. حالا یک ستون canonical اضافه می‌شود:

  * backfill با همان normalize_mobile برنامه (ترتیب id، قطعی)؛
  * شماره‌های معادلی که از قبل به دو حساب مختلف تعلق دارند شناسایی
    می‌شوند — رکورد دوم NULL می‌ماند (لاگینِ fallback با رشته‌ی خام
    کارش ادامه می‌دهد) تا مهاجرت روی داده‌ی کثیفِ موجود هرگز شکست
    نخورد؛
  * ایندکس یکتا روی مقدار canonical: از این پس ساختن دو حساب با
    شماره‌های معادل ناممکن است (IntegrityError → 409).

Revision ID: d2e6b4a8c1f5
Revises: c9f3a7d1e5b8
Create Date: 2026-09-26 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd2e6b4a8c1f5'
down_revision: Union[str, Sequence[str], None] = 'c9f3a7d1e5b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {c["name"] for c in inspector.get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {i["name"] for i in inspector.get_indexes(table_name)}


def upgrade() -> None:
    """Upgrade schema."""
    if 'mobile_normalized' not in _columns('users'):
        op.add_column(
            'users',
            sa.Column('mobile_normalized', sa.String(length=20), nullable=True),
        )

    # backfill — از منطق خود برنامه استفاده می‌شود تا تعریف canonical
    # دقیقاً یکی بماند (نه یک بازپیاده‌سازی SQL که drift کند).
    from app.core.text_normalization import normalize_mobile

    conn = op.get_bind()
    rows = conn.execute(sa.text('SELECT id, mobile FROM users ORDER BY id')).fetchall()
    taken: set[str] = set()
    for user_id, mobile in rows:
        canonical = normalize_mobile(mobile)
        if canonical is None:
            continue
        if canonical in taken:
            # دو حساب با شماره‌های معادل — داده‌ی از قبل متناقض. رکورد
            # جدیدتر NULL می‌ماند و لاگین با fallback رشته‌ی خام کار
            # می‌کند؛ رفع تعارض محتوا تصمیم عملیاتی است، نه مهاجرت.
            print(
                f"[d2e6b4a8c1f5] duplicate canonical mobile {canonical} "
                f"for user {user_id}; left NULL on purpose."
            )
            continue
        taken.add(canonical)
        conn.execute(
            sa.text('UPDATE users SET mobile_normalized = :canonical WHERE id = :uid'),
            {"canonical": canonical, "uid": user_id},
        )

    if 'uq_users_mobile_normalized' not in _indexes('users'):
        op.create_index(
            'uq_users_mobile_normalized',
            'users',
            ['mobile_normalized'],
            unique=True,
        )


def downgrade() -> None:
    """Downgrade schema."""
    if 'uq_users_mobile_normalized' in _indexes('users'):
        op.drop_index('uq_users_mobile_normalized', table_name='users')
    if 'mobile_normalized' in _columns('users'):
        op.drop_column('users', 'mobile_normalized')
