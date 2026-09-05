"""Добавить время последнего изменения товарного документа.

Revision ID: 0004_document_updated_at
Revises: 0003_allow_zero_money_posting
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_document_updated_at"
down_revision: str | None = "0003_allow_zero_money_posting"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "stock_documents",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_stock_documents_updated_at",
        "stock_documents",
        ["updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_stock_documents_updated_at", table_name="stock_documents")
    op.drop_column("stock_documents", "updated_at")
