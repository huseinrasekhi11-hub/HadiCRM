"""add products catalog and sale line items (structured per-product Rial sales)

Revision ID: e5b8d2f6a934
Revises: d4a7c1e85f23
Create Date: 2026-08-03 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e5b8d2f6a934'
down_revision: Union[str, Sequence[str], None] = 'd4a7c1e85f23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# کاتالوگ رسمی کالاها طبق فرآیند کسب‌وکار
CANONICAL_PRODUCTS = [
    "داکت اسپیلت",
    "فن کوئل",
    "چیلر",
    "اسپیلت",
    "کولر آبی",
    "پکیج",
    "رادیاتور",
    "شیرآلات",
    "هود سینک گاز",
    "سایر",
]


def upgrade() -> None:
    """Upgrade schema."""
    # Idempotency guards (see b0c1d2e3f4a5): create_all-bootstrapped
    # databases already contain these objects; skip cleanly.
    _insp = sa.inspect(op.get_bind())
    _tables = set(_insp.get_table_names())

    def _cols(table):
        return {c["name"] for c in _insp.get_columns(table)} if table in _tables else set()

    def _idx(table):
        return {ix["name"] for ix in _insp.get_indexes(table)} if table in _tables else set()

    # === کاتالوگ محصولات ===
    if 'products' not in _tables:
        op.create_table(
            'products',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('name'),
        )

    # === اقلام فروش (مبلغ ریالی به تفکیک کالا برای هر پرونده) ===
    if 'sale_line_items' not in _tables:
        op.create_table(
            'sale_line_items',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('lead_id', sa.Integer(), nullable=False),
            sa.Column('product_id', sa.Integer(), nullable=False),
            sa.Column('amount', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ),
            sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('lead_id', 'product_id', name='uq_sale_line_items_lead_product'),
        )
    if 'ix_sale_line_items_lead_id' not in _idx('sale_line_items'):
        op.create_index(op.f('ix_sale_line_items_lead_id'), 'sale_line_items', ['lead_id'], unique=False)
    if 'ix_sale_line_items_product_id' not in _idx('sale_line_items'):
        op.create_index(op.f('ix_sale_line_items_product_id'), 'sale_line_items', ['product_id'], unique=False)

    # === مقداردهی اولیه‌ی کاتالوگ ===
    products_table = sa.table(
        'products',
        sa.column('name', sa.String),
        sa.column('is_active', sa.Boolean),
    )
    existing_names = {
        row[0]
        for row in op.get_bind().execute(sa.text("SELECT name FROM products"))
    }
    missing = [n for n in CANONICAL_PRODUCTS if n not in existing_names]
    if missing:
        op.bulk_insert(
            products_table,
            [{"name": name, "is_active": True} for name in missing],
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_sale_line_items_product_id'), table_name='sale_line_items')
    op.drop_index(op.f('ix_sale_line_items_lead_id'), table_name='sale_line_items')
    op.drop_table('sale_line_items')
    op.drop_table('products')
