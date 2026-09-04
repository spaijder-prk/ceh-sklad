"""Добавить регистр текущих остатков.

Revision ID: 0002_current_balances
Revises: 0001_initial
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_current_balances"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "warehouse_stock_balances",
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=16, scale=3), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "quantity >= 0",
            name="ck_warehouse_stock_balance_nonnegative",
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"]),
        sa.PrimaryKeyConstraint("warehouse_id", "product_id"),
    )
    op.create_index(
        "ix_warehouse_stock_balances_product_id",
        "warehouse_stock_balances",
        ["product_id"],
        unique=False,
    )

    op.create_table(
        "representative_stock_balances",
        sa.Column("representative_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=16, scale=3), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "quantity >= 0",
            name="ck_representative_stock_balance_nonnegative",
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["representative_id"], ["representatives.id"]),
        sa.PrimaryKeyConstraint("representative_id", "product_id"),
    )
    op.create_index(
        "ix_representative_stock_balances_product_id",
        "representative_stock_balances",
        ["product_id"],
        unique=False,
    )

    op.execute(
        sa.text(
            """
            INSERT INTO warehouse_stock_balances
                (warehouse_id, product_id, quantity, updated_at)
            SELECT
                sp.warehouse_id,
                sp.product_id,
                SUM(sp.quantity),
                CURRENT_TIMESTAMP
            FROM stock_postings AS sp
            JOIN stock_documents AS sd ON sd.id = sp.document_id
            WHERE sp.warehouse_id IS NOT NULL
              AND sd.status = 'posted'
            GROUP BY sp.warehouse_id, sp.product_id
            HAVING SUM(sp.quantity) <> 0
            """
        )
    )

    op.execute(
        sa.text(
            """
            INSERT INTO representative_stock_balances
                (representative_id, product_id, quantity, updated_at)
            SELECT
                sp.representative_id,
                sp.product_id,
                SUM(sp.quantity),
                CURRENT_TIMESTAMP
            FROM stock_postings AS sp
            JOIN stock_documents AS sd ON sd.id = sp.document_id
            WHERE sp.representative_id IS NOT NULL
              AND sd.status = 'posted'
            GROUP BY sp.representative_id, sp.product_id
            HAVING SUM(sp.quantity) <> 0
            """
        )
    )


def downgrade() -> None:
    op.drop_index(
        "ix_representative_stock_balances_product_id",
        table_name="representative_stock_balances",
    )
    op.drop_table("representative_stock_balances")

    op.drop_index(
        "ix_warehouse_stock_balances_product_id",
        table_name="warehouse_stock_balances",
    )
    op.drop_table("warehouse_stock_balances")
