"""Начальная схема складского учета.

Revision ID: 0001_initial
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column(
            "role",
            sa.Enum("representative", "admin", "manager", name="userrole", native_enum=False),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_role", "users", ["role"], unique=False)

    op.create_table(
        "warehouses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_warehouses_code", "warehouses", ["code"], unique=True)

    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sku", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("retail_price", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("wholesale_price", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sku"),
    )
    op.create_index("ix_products_name", "products", ["name"], unique=False)
    op.create_index("ix_products_sku", "products", ["sku"], unique=True)

    op.create_table(
        "representatives",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_representatives_code", "representatives", ["code"], unique=True)

    op.create_table(
        "stock_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "document_type",
            sa.Enum(
                "receipt",
                "issue_to_representative",
                "representative_return",
                "warehouse_transfer",
                "sale",
                "adjustment",
                name="documenttype",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("posted", "cancelled", name="documentstatus", native_enum=False),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(length=128), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_id"),
    )
    op.create_index(
        "ix_stock_documents_document_type", "stock_documents", ["document_type"], unique=False
    )
    op.create_index("ix_stock_documents_external_id", "stock_documents", ["external_id"], unique=True)
    op.create_index("ix_stock_documents_status", "stock_documents", ["status"], unique=False)

    op.create_table(
        "stock_postings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=True),
        sa.Column("representative_id", sa.Uuid(), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=16, scale=3), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity <> 0", name="ck_stock_posting_nonzero_quantity"),
        sa.CheckConstraint(
            "(warehouse_id IS NOT NULL AND representative_id IS NULL) OR "
            "(warehouse_id IS NULL AND representative_id IS NOT NULL)",
            name="ck_stock_posting_single_owner",
        ),
        sa.ForeignKeyConstraint(["document_id"], ["stock_documents.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["representative_id"], ["representatives.id"]),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stock_postings_document_id", "stock_postings", ["document_id"], unique=False)
    op.create_index("ix_stock_postings_product_id", "stock_postings", ["product_id"], unique=False)
    op.create_index(
        "ix_stock_postings_representative_id", "stock_postings", ["representative_id"], unique=False
    )
    op.create_index("ix_stock_postings_warehouse_id", "stock_postings", ["warehouse_id"], unique=False)

    op.create_table(
        "money_postings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("representative_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column(
            "operation",
            sa.Enum("sale", "payment", "adjustment", name="moneyoperation", native_enum=False),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("external_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount <> 0", name="ck_money_posting_nonzero_amount"),
        sa.ForeignKeyConstraint(["document_id"], ["stock_documents.id"]),
        sa.ForeignKeyConstraint(["representative_id"], ["representatives.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_id"),
    )
    op.create_index("ix_money_postings_document_id", "money_postings", ["document_id"], unique=False)
    op.create_index("ix_money_postings_external_id", "money_postings", ["external_id"], unique=True)
    op.create_index("ix_money_postings_operation", "money_postings", ["operation"], unique=False)
    op.create_index(
        "ix_money_postings_representative_id", "money_postings", ["representative_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_money_postings_representative_id", table_name="money_postings")
    op.drop_index("ix_money_postings_operation", table_name="money_postings")
    op.drop_index("ix_money_postings_external_id", table_name="money_postings")
    op.drop_index("ix_money_postings_document_id", table_name="money_postings")
    op.drop_table("money_postings")

    op.drop_index("ix_stock_postings_warehouse_id", table_name="stock_postings")
    op.drop_index("ix_stock_postings_representative_id", table_name="stock_postings")
    op.drop_index("ix_stock_postings_product_id", table_name="stock_postings")
    op.drop_index("ix_stock_postings_document_id", table_name="stock_postings")
    op.drop_table("stock_postings")

    op.drop_index("ix_stock_documents_status", table_name="stock_documents")
    op.drop_index("ix_stock_documents_external_id", table_name="stock_documents")
    op.drop_index("ix_stock_documents_document_type", table_name="stock_documents")
    op.drop_table("stock_documents")

    op.drop_index("ix_representatives_code", table_name="representatives")
    op.drop_table("representatives")

    op.drop_index("ix_products_sku", table_name="products")
    op.drop_index("ix_products_name", table_name="products")
    op.drop_table("products")

    op.drop_index("ix_warehouses_code", table_name="warehouses")
    op.drop_table("warehouses")

    op.drop_index("ix_users_role", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
