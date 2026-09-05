"""Добавить управление доступом пользователей.

Revision ID: 0007_user_access_control
Revises: 0006_one_c_entity_links
Create Date: 2026-09-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0007_user_access_control"
down_revision: str | None = "0006_one_c_entity_links"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "users",
        sa.Column("auth_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index(op.f("ix_users_is_active"), "users", ["is_active"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_is_active"), table_name="users")
    op.drop_column("users", "auth_version")
    op.drop_column("users", "is_active")
