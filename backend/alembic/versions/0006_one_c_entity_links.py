"""Добавить постоянные соответствия сущностей 1С.

Revision ID: 0006_one_c_entity_links
Revises: 0005_operation_audit
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_one_c_entity_links"
down_revision: str | None = "0005_operation_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "one_c_entity_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("backend_id", sa.Uuid(), nullable=False),
        sa.Column("external_ref", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entity_type",
            "backend_id",
            name="uq_one_c_entity_links_backend",
        ),
        sa.UniqueConstraint(
            "entity_type",
            "external_ref",
            name="uq_one_c_entity_links_external_ref",
        ),
    )
    op.create_index(
        "ix_one_c_entity_links_entity_type",
        "one_c_entity_links",
        ["entity_type"],
        unique=False,
    )
    op.create_index(
        "ix_one_c_entity_links_backend_id",
        "one_c_entity_links",
        ["backend_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_one_c_entity_links_backend_id", table_name="one_c_entity_links")
    op.drop_index("ix_one_c_entity_links_entity_type", table_name="one_c_entity_links")
    op.drop_table("one_c_entity_links")
