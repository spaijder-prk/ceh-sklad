from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import PriceType, UserRole


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class BootstrapAdminRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    role: UserRole


class UserRead(ORMModel):
    id: UUID
    email: str
    full_name: str
    role: UserRole


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class WarehouseCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)


class WarehouseRead(ORMModel):
    id: UUID
    code: str
    name: str


class RepresentativeCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    user_id: UUID | None = None


class RepresentativeRead(ORMModel):
    id: UUID
    code: str
    name: str
    user_id: UUID | None


class ProductCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    unit: str = Field(default="шт", min_length=1, max_length=32)
    retail_price: Decimal = Field(ge=0, decimal_places=2)
    wholesale_price: Decimal = Field(ge=0, decimal_places=2)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    unit: str | None = Field(default=None, min_length=1, max_length=32)
    retail_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    wholesale_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)

    @model_validator(mode="after")
    def validate_changes(self):
        if all(
            value is None
            for value in (self.name, self.unit, self.retail_price, self.wholesale_price)
        ):
            raise ValueError("Необходимо передать хотя бы одно изменяемое поле")
        return self


class ProductRead(ORMModel):
    id: UUID
    sku: str
    name: str
    unit: str
    retail_price: Decimal
    wholesale_price: Decimal


class QuantityLine(BaseModel):
    product_id: UUID
    quantity: Decimal = Field(gt=0, decimal_places=3)


class SaleLine(QuantityLine):
    price_type: PriceType = PriceType.RETAIL


class BaseOperation(BaseModel):
    comment: str | None = Field(default=None, max_length=2000)
    external_id: str | None = Field(default=None, max_length=128)


class ReceiptRequest(BaseOperation):
    warehouse_id: UUID
    lines: list[QuantityLine] = Field(min_length=1)


class IssueRequest(BaseOperation):
    warehouse_id: UUID
    representative_id: UUID
    lines: list[QuantityLine] = Field(min_length=1)


class TransferRequest(BaseOperation):
    source_warehouse_id: UUID
    target_warehouse_id: UUID
    lines: list[QuantityLine] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_different_warehouses(self):
        if self.source_warehouse_id == self.target_warehouse_id:
            raise ValueError("Склад-источник и склад-получатель должны отличаться")
        return self


class ReturnRequest(BaseOperation):
    representative_id: UUID
    warehouse_id: UUID
    lines: list[QuantityLine] = Field(min_length=1)


class SaleRequest(BaseOperation):
    representative_id: UUID
    lines: list[SaleLine] = Field(min_length=1)


class PaymentRequest(BaseOperation):
    representative_id: UUID
    amount: Decimal = Field(gt=0, decimal_places=2)


class OperationResult(BaseModel):
    document_id: UUID | None = None
    money_posting_id: UUID | None = None
    debt_delta: Decimal = Decimal("0")


class WarehouseBalanceLine(BaseModel):
    warehouse_id: UUID
    warehouse_code: str
    warehouse_name: str
    product_id: UUID
    sku: str
    product_name: str
    unit: str
    retail_price: Decimal
    wholesale_price: Decimal
    quantity: Decimal


class RepresentativeBalanceLine(BaseModel):
    representative_id: UUID
    representative_code: str
    representative_name: str
    product_id: UUID
    sku: str
    product_name: str
    unit: str
    retail_price: Decimal
    wholesale_price: Decimal
    quantity: Decimal


class RepresentativeDebt(BaseModel):
    representative_id: UUID
    debt: Decimal
