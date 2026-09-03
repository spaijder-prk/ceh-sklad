"""Начальная схема учета склада.

Идентификатор: 20260903_01
Предыдущая версия: нет
Дата: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa

revision = "20260903_01"
down_revision = None
branch_labels = None
depends_on = None

user_role = sa.Enum("REPRESENTATIVE", "ADMIN", "MANAGER", name="userrole")
location_kind = sa.Enum("WAREHOUSE", "REPRESENTATIVE", name="locationkind")
stock_document_kind = sa.Enum(
    "TRANSFER",
    "ISSUE_TO_REPRESENTATIVE",
    "REPRESENTATIVE_RETURN",
    "SALE",
    "ADJUSTMENT",
    name="stockdocumentkind",
)
money_transaction_kind = sa.Enum("SALE", "CASH_HANDOVER", "ADJUSTMENT", name="moneytransactionkind")


def upgrade() -> None:
    op.create_table(
        "locations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("kind", location_kind, nullable=False),
        sa.Column("external_1c_id", sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_1c_id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sku", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("unit_name", sa.String(length=30), nullable=False),
        sa.Column("retail_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("wholesale_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("external_1c_id", sa.String(length=100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_1c_id"),
    )
    op.create_index("ix_products_name", "products", ["name"], unique=False)
    op.create_index("ix_products_sku", "products", ["sku"], unique=True)
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("login", sa.String(length=100), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("login"),
    )
    op.create_table(
        "inventory_balances",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Numeric(16, 3), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("location_id", "product_id", name="uq_balance_location_product"),
    )
    op.create_index("ix_inventory_balances_location_id", "inventory_balances", ["location_id"], unique=False)
    op.create_index("ix_inventory_balances_product_id", "inventory_balances", ["product_id"], unique=False)
    op.create_table(
        "stock_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", stock_document_kind, nullable=False),
        sa.Column("source_location_id", sa.Uuid(), nullable=True),
        sa.Column("destination_location_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("comment", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["destination_location_id"], ["locations.id"]),
        sa.ForeignKeyConstraint(["source_location_id"], ["locations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stock_documents_created_at", "stock_documents", ["created_at"], unique=False)
    op.create_index("ix_stock_documents_kind", "stock_documents", ["kind"], unique=False)
    op.create_table(
        "stock_document_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Numeric(16, 3), nullable=False),
        sa.Column("unit_price", sa.Numeric(14, 2), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["stock_documents.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stock_document_lines_document_id", "stock_document_lines", ["document_id"], unique=False)
    op.create_index("ix_stock_document_lines_product_id", "stock_document_lines", ["product_id"], unique=False)
    op.create_table(
        "stock_movements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity_delta", sa.Numeric(16, 3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["stock_documents.id"]),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stock_movements_created_at", "stock_movements", ["created_at"], unique=False)
    op.create_index("ix_stock_movements_document_id", "stock_movements", ["document_id"], unique=False)
    op.create_index("ix_stock_movements_location_id", "stock_movements", ["location_id"], unique=False)
    op.create_index("ix_stock_movements_product_id", "stock_movements", ["product_id"], unique=False)
    op.create_table(
        "money_transactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("representative_location_id", sa.Uuid(), nullable=False),
        sa.Column("kind", money_transaction_kind, nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("stock_document_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("comment", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["representative_location_id"], ["locations.id"]),
        sa.ForeignKeyConstraint(["stock_document_id"], ["stock_documents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_money_transactions_created_at", "money_transactions", ["created_at"], unique=False)
    op.create_index("ix_money_transactions_kind", "money_transactions", ["kind"], unique=False)
    op.create_index("ix_money_transactions_representative_location_id", "money_transactions", ["representative_location_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_money_transactions_representative_location_id", table_name="money_transactions")
    op.drop_index("ix_money_transactions_kind", table_name="money_transactions")
    op.drop_index("ix_money_transactions_created_at", table_name="money_transactions")
    op.drop_table("money_transactions")
    op.drop_index("ix_stock_movements_product_id", table_name="stock_movements")
    op.drop_index("ix_stock_movements_location_id", table_name="stock_movements")
    op.drop_index("ix_stock_movements_document_id", table_name="stock_movements")
    op.drop_index("ix_stock_movements_created_at", table_name="stock_movements")
    op.drop_table("stock_movements")
    op.drop_index("ix_stock_document_lines_product_id", table_name="stock_document_lines")
    op.drop_index("ix_stock_document_lines_document_id", table_name="stock_document_lines")
    op.drop_table("stock_document_lines")
    op.drop_index("ix_stock_documents_kind", table_name="stock_documents")
    op.drop_index("ix_stock_documents_created_at", table_name="stock_documents")
    op.drop_table("stock_documents")
    op.drop_index("ix_inventory_balances_product_id", table_name="inventory_balances")
    op.drop_index("ix_inventory_balances_location_id", table_name="inventory_balances")
    op.drop_table("inventory_balances")
    op.drop_table("users")
    op.drop_index("ix_products_sku", table_name="products")
    op.drop_index("ix_products_name", table_name="products")
    op.drop_table("products")
    op.drop_table("locations")
    money_transaction_kind.drop(op.get_bind(), checkfirst=True)
    stock_document_kind.drop(op.get_bind(), checkfirst=True)
    user_role.drop(op.get_bind(), checkfirst=True)
    location_kind.drop(op.get_bind(), checkfirst=True)
