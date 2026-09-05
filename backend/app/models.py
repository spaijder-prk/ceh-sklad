from __future__ import annotations

from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from .db import Base


MONEY_STEP = Decimal("0.01")


class UserRole(StrEnum):
    REPRESENTATIVE = "representative"
    ADMIN = "admin"
    MANAGER = "manager"


class DocumentType(StrEnum):
    RECEIPT = "receipt"
    ISSUE_TO_REPRESENTATIVE = "issue_to_representative"
    REPRESENTATIVE_RETURN = "representative_return"
    WAREHOUSE_TRANSFER = "warehouse_transfer"
    SALE = "sale"
    ADJUSTMENT = "adjustment"


class DocumentStatus(StrEnum):
    POSTED = "posted"
    CANCELLED = "cancelled"


class MoneyOperation(StrEnum):
    SALE = "sale"
    PAYMENT = "payment"
    ADJUSTMENT = "adjustment"


class PriceType(StrEnum):
    RETAIL = "retail"
    WHOLESALE = "wholesale"


def value_enum(enum_type):
    return Enum(
        enum_type,
        values_callable=lambda members: [member.value for member in members],
        native_enum=False,
    )


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(value_enum(UserRole), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Warehouse(Base):
    __tablename__ = "warehouses"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Representative(Base):
    __tablename__ = "representatives"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    user_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    sku: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    unit: Mapped[str] = mapped_column(String(32), default="шт")
    retail_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    wholesale_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StockDocument(Base):
    __tablename__ = "stock_documents"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    document_type: Mapped[DocumentType] = mapped_column(value_enum(DocumentType), index=True)
    status: Mapped[DocumentStatus] = mapped_column(
        value_enum(DocumentStatus), default=DocumentStatus.POSTED, index=True
    )
    external_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True, index=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, index=True
    )

    postings: Mapped[list[StockPosting]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class StockPosting(Base):
    __tablename__ = "stock_postings"
    __table_args__ = (
        CheckConstraint(
            "(warehouse_id IS NOT NULL AND representative_id IS NULL) OR "
            "(warehouse_id IS NULL AND representative_id IS NOT NULL)",
            name="ck_stock_posting_single_owner",
        ),
        CheckConstraint("quantity <> 0", name="ck_stock_posting_nonzero_quantity"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("stock_documents.id"), index=True)
    product_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("products.id"), index=True)
    warehouse_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("warehouses.id"), nullable=True, index=True)
    representative_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("representatives.id"), nullable=True, index=True
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(16, 3))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    document: Mapped[StockDocument] = relationship(back_populates="postings")
    product: Mapped[Product] = relationship()


class WarehouseStockBalance(Base):
    __tablename__ = "warehouse_stock_balances"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_warehouse_stock_balance_nonnegative"),
    )

    warehouse_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("warehouses.id"), primary_key=True
    )
    product_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("products.id"), primary_key=True, index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(16, 3), default=Decimal("0"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class RepresentativeStockBalance(Base):
    __tablename__ = "representative_stock_balances"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_representative_stock_balance_nonnegative"),
    )

    representative_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("representatives.id"), primary_key=True
    )
    product_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("products.id"), primary_key=True, index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(16, 3), default=Decimal("0"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class MoneyPosting(Base):
    __tablename__ = "money_postings"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    representative_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("representatives.id"), index=True)
    document_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("stock_documents.id"), nullable=True, index=True
    )
    operation: Mapped[MoneyOperation] = mapped_column(value_enum(MoneyOperation), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    @validates("amount")
    def normalize_amount(self, _, value: Decimal) -> Decimal:
        return Decimal(value).quantize(MONEY_STEP, rounding=ROUND_HALF_UP)
