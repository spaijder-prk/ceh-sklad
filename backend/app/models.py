from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class UserRole(str, enum.Enum):
    REPRESENTATIVE = "representative"
    ADMIN = "admin"
    MANAGER = "manager"


class LocationKind(str, enum.Enum):
    WAREHOUSE = "warehouse"
    REPRESENTATIVE = "representative"


class StockDocumentKind(str, enum.Enum):
    TRANSFER = "transfer"
    ISSUE_TO_REPRESENTATIVE = "issue_to_representative"
    REPRESENTATIVE_RETURN = "representative_return"
    SALE = "sale"
    ADJUSTMENT = "adjustment"


class MoneyTransactionKind(str, enum.Enum):
    SALE = "sale"
    CASH_HANDOVER = "cash_handover"
    ADJUSTMENT = "adjustment"


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(150), unique=True)
    kind: Mapped[LocationKind] = mapped_column(Enum(LocationKind))
    external_1c_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(150))
    login: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole))
    location_id: Mapped[UUID | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)

    location: Mapped[Location | None] = relationship()


class Product(Base):
    __tablename__ = "products"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    sku: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    unit_name: Mapped[str] = mapped_column(String(30), default="шт")
    retail_price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    wholesale_price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    external_1c_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)


class InventoryBalance(Base):
    __tablename__ = "inventory_balances"
    __table_args__ = (UniqueConstraint("location_id", "product_id", name="uq_balance_location_product"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    location_id: Mapped[UUID] = mapped_column(ForeignKey("locations.id"), index=True)
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id"), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(16, 3), default=Decimal("0"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    location: Mapped[Location] = relationship()
    product: Mapped[Product] = relationship()


class StockDocument(Base):
    __tablename__ = "stock_documents"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    kind: Mapped[StockDocumentKind] = mapped_column(Enum(StockDocumentKind), index=True)
    source_location_id: Mapped[UUID | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    destination_location_id: Mapped[UUID | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    created_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    comment: Mapped[str | None] = mapped_column(String(500), nullable=True)
    external_1c_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    synced_1c_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    client_operation_key: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    client_payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class StockDocumentLine(Base):
    __tablename__ = "stock_document_lines"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(ForeignKey("stock_documents.id"), index=True)
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id"), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(16, 3))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(ForeignKey("stock_documents.id"), index=True)
    location_id: Mapped[UUID] = mapped_column(ForeignKey("locations.id"), index=True)
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id"), index=True)
    quantity_delta: Mapped[Decimal] = mapped_column(Numeric(16, 3))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class MoneyTransaction(Base):
    __tablename__ = "money_transactions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    representative_location_id: Mapped[UUID] = mapped_column(ForeignKey("locations.id"), index=True)
    kind: Mapped[MoneyTransactionKind] = mapped_column(Enum(MoneyTransactionKind), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    stock_document_id: Mapped[UUID | None] = mapped_column(ForeignKey("stock_documents.id"), nullable=True)
    created_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    comment: Mapped[str | None] = mapped_column(String(500), nullable=True)
    external_1c_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    synced_1c_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    client_operation_key: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    client_payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class IntegrationExchangeLog(Base):
    __tablename__ = "integration_exchange_logs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    direction: Mapped[str] = mapped_column(String(20), index=True)
    operation_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), index=True)
    entity_internal_id: Mapped[UUID | None] = mapped_column(nullable=True)
    external_1c_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    actor_type: Mapped[str] = mapped_column(String(20), index=True)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(300), index=True)
    status_code: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
