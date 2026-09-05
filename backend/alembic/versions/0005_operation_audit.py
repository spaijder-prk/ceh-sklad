"""Добавить аудит сторно и денежных проводок.

Revision ID: 0005_operation_audit
Revises: 0004_document_updated_at
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_operation_audit"
down_revision: str | None = "0004_document_updated_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("stock_documents") as batch:
        batch.add_column(sa.Column("cancelled_by_user_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key(
            "fk_stock_documents_cancelled_by_user_id_users",
            "users",
            ["cancelled_by_user_id"],
            ["id"],
        )

    with op.batch_alter_table("money_postings") as batch:
        batch.add_column(sa.Column("created_by_user_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_money_postings_created_by_user_id_users",
            "users",
            ["created_by_user_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("money_postings") as batch:
        batch.drop_constraint(
            "fk_money_postings_created_by_user_id_users",
            type_="foreignkey",
        )
        batch.drop_column("created_by_user_id")

    with op.batch_alter_table("stock_documents") as batch:
        batch.drop_constraint(
            "fk_stock_documents_cancelled_by_user_id_users",
            type_="foreignkey",
        )
        batch.drop_column("cancelled_at")
        batch.drop_column("cancelled_by_user_id")
