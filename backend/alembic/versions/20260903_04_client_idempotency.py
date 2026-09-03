"""Ключи идемпотентности мобильных операций.

Идентификатор: 20260903_04
Предыдущая версия: 20260903_03
Дата: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa

revision = "20260903_04"
down_revision = "20260903_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stock_documents", sa.Column("client_operation_key", sa.String(length=120), nullable=True))
    op.add_column("stock_documents", sa.Column("client_payload_hash", sa.String(length=64), nullable=True))
    op.create_unique_constraint("uq_stock_documents_client_operation_key", "stock_documents", ["client_operation_key"])

    op.add_column("money_transactions", sa.Column("client_operation_key", sa.String(length=120), nullable=True))
    op.add_column("money_transactions", sa.Column("client_payload_hash", sa.String(length=64), nullable=True))
    op.create_unique_constraint("uq_money_transactions_client_operation_key", "money_transactions", ["client_operation_key"])


def downgrade() -> None:
    op.drop_constraint("uq_money_transactions_client_operation_key", "money_transactions", type_="unique")
    op.drop_column("money_transactions", "client_payload_hash")
    op.drop_column("money_transactions", "client_operation_key")
    op.drop_constraint("uq_stock_documents_client_operation_key", "stock_documents", type_="unique")
    op.drop_column("stock_documents", "client_payload_hash")
    op.drop_column("stock_documents", "client_operation_key")
