"""baseline: create core tables (leads, tasks, activities) and align users

Revision ID: b0c1d2e3f4a5
Revises: 8b8eab149c37
Create Date: 2026-09-22

Why this migration exists
-------------------------
The historical chain created ``users`` (6ea849d71db2) and ``audit_logs``
(8b8eab149c37) but the core CRM tables ``leads`` / ``tasks`` /
``activities`` were only ever created by ``Base.metadata.create_all``
(app/scripts/create_tables.py). As a result, ``alembic upgrade head`` on
a fresh database failed at f1e1afa48353 with:

    psycopg2.errors.UndefinedTable: relation "leads" does not exist

which also broke ``docker compose up`` (the ``migrate`` service must
complete successfully before the API starts).

The ``users`` table created by 6ea849d71db2 additionally does not match
app/models/user.py: the model requires ``mobile``, ``role`` and
``permissions`` columns (and does not have ``username``/``email``).

This baseline is deliberately IDEMPOTENT: every DDL statement is guarded
by an inspector check, so databases that were bootstrapped with
create_all (or partially migrated) pass through untouched.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b0c1d2e3f4a5'
down_revision: Union[str, Sequence[str], None] = '8b8eab149c37'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector():
    return sa.inspect(op.get_bind())


def _tables():
    return set(_inspector().get_table_names())


def _columns(table: str) -> dict[str, dict]:
    return {c["name"]: c for c in _inspector().get_columns(table)}


def _row_count(table: str) -> int:
    conn = op.get_bind()
    return conn.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0


def upgrade() -> None:
    tables = _tables()

    # ------------------------------------------------------------------
    # leads (baseline schema = current model minus columns added by
    # f1e1afa48353, 77b3ba45c39a, a3f9c7d21b44 and c9d2e7b4a1f8)
    # ------------------------------------------------------------------
    if "leads" not in tables:
        op.create_table(
            'leads',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('customer_name', sa.String(length=100), nullable=False),
            sa.Column('mobile', sa.String(length=20), nullable=False),
            sa.Column('source', sa.String(length=50), nullable=False),
            sa.Column('need', sa.String(length=500), nullable=True),
            sa.Column('status', sa.String(length=50), nullable=False),
            sa.Column('created_by_id', sa.Integer(), nullable=False),
            sa.Column('owner_id', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            # legacy / phased columns
            sa.Column('sla_notified', sa.Boolean(), nullable=True),
            sa.Column('needs_list', sa.JSON(), nullable=True),
            sa.Column('loss_reason', sa.String(), nullable=True),
            sa.Column('status_updated_at', sa.DateTime(), nullable=True),
            sa.Column('stagnant_warned', sa.Boolean(), nullable=True),
            sa.Column('is_escalated', sa.Boolean(), nullable=True),
            sa.Column('score', sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
            sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_leads_mobile'), 'leads', ['mobile'], unique=False)

    # ------------------------------------------------------------------
    # tasks (baseline = model minus is_deleted/deleted_at)
    # ------------------------------------------------------------------
    if "tasks" not in tables:
        op.create_table(
            'tasks',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('lead_id', sa.Integer(), nullable=False),
            sa.Column('created_by_id', sa.Integer(), nullable=False),
            sa.Column('assigned_to_id', sa.Integer(), nullable=False),
            sa.Column('title', sa.String(length=100), nullable=False),
            sa.Column('description', sa.String(length=1000), nullable=True),
            sa.Column('due_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('status', sa.String(length=50), nullable=False),
            sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('is_notified', sa.Boolean(), nullable=True),
            sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ),
            sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
            sa.ForeignKeyConstraint(['assigned_to_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_tasks_lead_id'), 'tasks', ['lead_id'], unique=False)
        op.create_index(
            op.f('ix_tasks_assigned_to_id'), 'tasks', ['assigned_to_id'], unique=False
        )
        op.create_index(op.f('ix_tasks_due_at'), 'tasks', ['due_at'], unique=False)

    # ------------------------------------------------------------------
    # activities (baseline = model minus outcome/next_follow_up/
    # no_followup_reason which a3f9c7d21b44 adds)
    # ------------------------------------------------------------------
    if "activities" not in tables:
        op.create_table(
            'activities',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('lead_id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('activity_type', sa.String(length=50), nullable=False),
            sa.Column('title', sa.String(length=100), nullable=False),
            sa.Column('description', sa.String(length=1000), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(
            op.f('ix_activities_lead_id'), 'activities', ['lead_id'], unique=False
        )

    # ------------------------------------------------------------------
    # users: align 6ea849d71db2/e84148be659e schema with app/models/user.py
    # ------------------------------------------------------------------
    users_cols = _columns("users")
    users_empty = _row_count("users") == 0

    if "mobile" not in users_cols:
        op.add_column("users", sa.Column("mobile", sa.String(length=20), nullable=True))
        # deterministic placeholder per row so NOT NULL + UNIQUE can be set
        op.execute(
            "UPDATE users SET mobile = '0' || lpad(id::text, 11, '0') "
            "WHERE mobile IS NULL"
        )
        op.alter_column("users", "mobile", nullable=False)
        op.create_unique_constraint("uq_users_mobile", "users", ["mobile"])

    if "role" not in users_cols:
        op.add_column("users", sa.Column("role", sa.String(length=50), nullable=True))
        op.execute(
            "UPDATE users SET role = CASE WHEN is_superuser THEN 'Admin' "
            "ELSE 'Sales' END WHERE role IS NULL"
        )
        op.alter_column("users", "role", nullable=False)

    if "permissions" not in users_cols:
        op.add_column("users", sa.Column("permissions", sa.JSON(), nullable=True))

    # username/email exist only in the migration-created schema; the model
    # has no such fields and the ORM never populates them. Remove them on
    # an empty table (a fresh alembic-only install); otherwise just relax
    # NOT NULL so ORM inserts do not violate the constraint.
    if "username" in users_cols:
        if users_empty:
            op.drop_column("users", "username")
        elif users_cols["username"].get("nullable") is False:
            op.alter_column("users", "username", nullable=True)
    if "email" in users_cols and users_empty:
        op.drop_column("users", "email")

    # 6ea849d71db2 created full_name as VARCHAR(120); the model says
    # String(100). Shrink only when no row would be truncated.
    fn = users_cols.get("full_name")
    if fn is not None and str(fn["type"]).upper() == "VARCHAR(120)":
        maxlen = op.get_bind().execute(
            sa.text("SELECT COALESCE(MAX(length(full_name)), 0) FROM users")
        ).scalar()
        if maxlen <= 100:
            op.alter_column(
                "users", "full_name", type_=sa.String(length=100),
                existing_nullable=fn.get("nullable", False),
            )

    # created_at/updated_at/last_login are tz-aware in the model but were
    # created as naive TIMESTAMP by the early migrations.
    for col in ("created_at", "updated_at", "last_login"):
        info = _columns("users").get(col)
        if info is None:
            continue
        coltype = info["type"]
        if isinstance(coltype, sa.DateTime) and not coltype.timezone:
            op.alter_column(
                "users",
                col,
                type_=sa.DateTime(timezone=True),
                existing_nullable=info.get("nullable", True),
                postgresql_using=f"{col} AT TIME ZONE 'UTC'",
            )


def downgrade() -> None:
    # SECURITY/DATA-LOSS GUARD: this baseline is deliberately idempotent —
    # it may discover that leads/tasks/activities already exist because an
    # older deployment created them outside Alembic (create_all era). There
    # is no durable marker telling us whether THIS revision created each
    # table, so an automated downgrade here could silently drop production
    # CRM tables full of customer data. The rollback is therefore refused
    # on purpose; operators must perform a reviewed manual rollback or a
    # backup restore instead.
    raise RuntimeError(
        "Downgrading the b0c1d2e3f4a5 baseline is disabled on purpose: it "
        "cannot distinguish tables this migration created from pre-existing "
        "production tables, and dropping them would destroy CRM data. Use a "
        "reviewed manual rollback or restore from backup instead."
    )
