"""Связи одной операции с несколькими внешними документами УНФ.

Идентификатор: 20260903_08
Предыдущая версия: 20260903_07
Дата: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa

revision = "20260903_08"
down_revision = "20260903_07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_export_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_internal_id", sa.Uuid(), nullable=False),
        sa.Column("external_1c_id", sa.String(length=100), nullable=False),
        sa.Column("external_kind", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entity_type",
            "external_1c_id",
            name="uq_integration_export_links_entity_external",
        ),
        sa.UniqueConstraint(
            "entity_type",
            "entity_internal_id",
            "external_1c_id",
            name="uq_integration_export_links_internal_external",
        ),
    )
    op.create_index(
        op.f("ix_integration_export_links_entity_type"),
        "integration_export_links",
        ["entity_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_integration_export_links_entity_internal_id"),
        "integration_export_links",
        ["entity_internal_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_integration_export_links_external_1c_id"),
        "integration_export_links",
        ["external_1c_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_integration_export_links_created_at"),
        "integration_export_links",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_integration_export_links_created_at"), table_name="integration_export_links")
    op.drop_index(op.f("ix_integration_export_links_external_1c_id"), table_name="integration_export_links")
    op.drop_index(op.f("ix_integration_export_links_entity_internal_id"), table_name="integration_export_links")
    op.drop_index(op.f("ix_integration_export_links_entity_type"), table_name="integration_export_links")
    op.drop_table("integration_export_links")
