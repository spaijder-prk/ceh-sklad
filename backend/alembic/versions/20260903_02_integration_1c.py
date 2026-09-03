"""Промышленный контур интеграции с 1С.

Идентификатор: 20260903_02
Предыдущая версия: 20260903_01
Дата: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa

revision = "20260903_02"
down_revision = "20260903_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stock_documents", sa.Column("external_1c_id", sa.String(length=100), nullable=True))
    op.add_column("stock_documents", sa.Column("synced_1c_at", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint("uq_stock_documents_external_1c_id", "stock_documents", ["external_1c_id"])

    op.add_column("money_transactions", sa.Column("external_1c_id", sa.String(length=100), nullable=True))
    op.add_column("money_transactions", sa.Column("synced_1c_at", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint("uq_money_transactions_external_1c_id", "money_transactions", ["external_1c_id"])

    op.create_table(
        "integration_exchange_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("operation_key", sa.String(length=120), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_internal_id", sa.Uuid(), nullable=True),
        sa.Column("external_1c_id", sa.String(length=100), nullable=True),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_integration_exchange_logs_created_at", "integration_exchange_logs", ["created_at"], unique=False)
    op.create_index("ix_integration_exchange_logs_direction", "integration_exchange_logs", ["direction"], unique=False)
    op.create_index("ix_integration_exchange_logs_entity_type", "integration_exchange_logs", ["entity_type"], unique=False)
    op.create_index("ix_integration_exchange_logs_external_1c_id", "integration_exchange_logs", ["external_1c_id"], unique=False)
    op.create_index("ix_integration_exchange_logs_operation_key", "integration_exchange_logs", ["operation_key"], unique=True)
    op.create_index("ix_integration_exchange_logs_status", "integration_exchange_logs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_integration_exchange_logs_status", table_name="integration_exchange_logs")
    op.drop_index("ix_integration_exchange_logs_operation_key", table_name="integration_exchange_logs")
    op.drop_index("ix_integration_exchange_logs_external_1c_id", table_name="integration_exchange_logs")
    op.drop_index("ix_integration_exchange_logs_entity_type", table_name="integration_exchange_logs")
    op.drop_index("ix_integration_exchange_logs_direction", table_name="integration_exchange_logs")
    op.drop_index("ix_integration_exchange_logs_created_at", table_name="integration_exchange_logs")
    op.drop_table("integration_exchange_logs")
    op.drop_constraint("uq_money_transactions_external_1c_id", "money_transactions", type_="unique")
    op.drop_column("money_transactions", "synced_1c_at")
    op.drop_column("money_transactions", "external_1c_id")
    op.drop_constraint("uq_stock_documents_external_1c_id", "stock_documents", type_="unique")
    op.drop_column("stock_documents", "synced_1c_at")
    op.drop_column("stock_documents", "external_1c_id")
