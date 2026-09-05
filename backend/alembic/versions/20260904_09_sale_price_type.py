"""Сохраняем тип цены продажи для точного экспорта в УНФ.

Идентификатор: 20260904_09
Предыдущая версия: 20260903_08
Дата: 2026-09-04
"""
from alembic import op
import sqlalchemy as sa

revision = "20260904_09"
down_revision = "20260903_08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stock_documents",
        sa.Column("sale_price_type", sa.String(length=20), nullable=True),
    )
    op.create_check_constraint(
        "ck_stock_documents_sale_price_type_valid",
        "stock_documents",
        "sale_price_type IS NULL OR sale_price_type IN ('retail', 'wholesale')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_stock_documents_sale_price_type_valid",
        "stock_documents",
        type_="check",
    )
    op.drop_column("stock_documents", "sale_price_type")
