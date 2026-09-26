from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "add_mobile_normalized"
down_revision = None  # CHANGE THIS if your repo already has a migration head
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # create_tables.py currently creates the table before migrations run.
    if "users" not in inspector.get_table_names():
        return

    columns = {
        column["name"]
        for column in inspector.get_columns("users")
    }

    if "mobile_normalized" not in columns:
        op.add_column(
            "users",
            sa.Column(
                "mobile_normalized",
                sa.String(length=20),
                nullable=True,
            ),
        )

    indexes = {
        index["name"]
        for index in inspector.get_indexes("users")
    }

    if "uq_users_mobile_normalized" not in indexes:
        op.create_index(
            "uq_users_mobile_normalized",
            "users",
            ["mobile_normalized"],
            unique=True,
            postgresql_where=sa.text("mobile_normalized IS NOT NULL"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "users" not in inspector.get_table_names():
        return

    indexes = {
        index["name"]
        for index in inspector.get_indexes("users")
    }

    if "uq_users_mobile_normalized" in indexes:
        op.drop_index(
            "uq_users_mobile_normalized",
            table_name="users",
        )

    columns = {
        column["name"]
        for column in inspector.get_columns("users")
    }

    if "mobile_normalized" in columns:
        op.drop_column("users", "mobile_normalized")
