"""Инварианты цен, остатков и строк документов.

Идентификатор: 20260903_06
Предыдущая версия: 20260903_05
Дата: 2026-09-03
"""
from alembic import op

revision = "20260903_06"
down_revision = "20260903_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_products_retail_price_nonnegative",
        "products",
        "retail_price >= 0",
    )
    op.create_check_constraint(
        "ck_products_wholesale_price_nonnegative",
        "products",
        "wholesale_price >= 0",
    )
    op.create_check_constraint(
        "ck_inventory_balances_quantity_nonnegative",
        "inventory_balances",
        "quantity >= 0",
    )
    op.create_check_constraint(
        "ck_stock_document_lines_quantity_positive",
        "stock_document_lines",
        "quantity > 0",
    )
    op.create_check_constraint(
        "ck_stock_document_lines_unit_price_nonnegative",
        "stock_document_lines",
        "unit_price IS NULL OR unit_price >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_stock_document_lines_unit_price_nonnegative", "stock_document_lines", type_="check")
    op.drop_constraint("ck_stock_document_lines_quantity_positive", "stock_document_lines", type_="check")
    op.drop_constraint("ck_inventory_balances_quantity_nonnegative", "inventory_balances", type_="check")
    op.drop_constraint("ck_products_wholesale_price_nonnegative", "products", type_="check")
    op.drop_constraint("ck_products_retail_price_nonnegative", "products", type_="check")
