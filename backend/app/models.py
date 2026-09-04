from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


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


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, native_enum=False), index=True)
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
    document_type: Mapped[DocumentType] = mapped_column(Enum(DocumentType, native_enum=False), index=True)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, native_enum=False), default=DocumentStatus.POSTED, index=True
    )
    external_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True, index=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

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


class MoneyPosting(Base):
    __tablename__ = "money_postings"
    __table_args__ = (CheckConstraint("amount <> 0", name="ck_money_posting_nonzero_amount"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    representative_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("representatives.id"), index=True)
    document_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("stock_documents.id"), nullable=True, index=True
    )
    operation: Mapped[MoneyOperation] = mapped_column(Enum(MoneyOperation, native_enum=False), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
