from alembic import op
import sqlalchemy as sa

revision = "add_mobile_normalized"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS mobile_normalized VARCHAR(20)
            """
        )
    )

    op.execute(
        sa.text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_users_mobile_normalized
            ON users (mobile_normalized)
            WHERE mobile_normalized IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DROP INDEX IF EXISTS uq_users_mobile_normalized
            """
        )
    )

    op.execute(
        sa.text(
            """
            ALTER TABLE users
            DROP COLUMN IF EXISTS mobile_normalized
            """
        )
    )
