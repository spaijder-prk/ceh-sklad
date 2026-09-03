"""Безопасное архивирование мест хранения.

Идентификатор: 20260903_05
Предыдущая версия: 20260903_04
Дата: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa

revision = "20260903_05"
down_revision = "20260903_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "locations",
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("locations", "is_active")
