from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field

from .models import LocationKind, UserRole


class PriceType(str, Enum):
    RETAIL = "retail"
    WHOLESALE = "wholesale"


class LoginIn(BaseModel):
    login: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: UUID
    name: str
    login: str
    role: str
    location_id: UUID | None


class UserCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    login: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=10, max_length=128)
    role: UserRole
    location_id: UUID | None = None


class LocationOut(BaseModel):
    id: UUID
    name: str
    kind: LocationKind
    external_1c_id: str | None

    model_config = {"from_attributes": True}


class LocationCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    kind: LocationKind
    external_1c_id: str | None = Field(default=None, max_length=100)


class ProductOut(BaseModel):
    id: UUID
    sku: str
    name: str
    unit_name: str
    retail_price: Decimal
    wholesale_price: Decimal

    model_config = {"from_attributes": True}


class ProductCreateIn(BaseModel):
    sku: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=2, max_length=200)
    unit_name: str = Field(default="шт", min_length=1, max_length=30)
    retail_price: Decimal = Field(ge=0)
    wholesale_price: Decimal = Field(ge=0)
    external_1c_id: str | None = Field(default=None, max_length=100)


class StockItemOut(BaseModel):
    location_id: UUID
    location_name: str
    product_id: UUID
    sku: str
    product_name: str
    unit_name: str
    quantity: Decimal
    retail_price: Decimal
    wholesale_price: Decimal


class MovementItemIn(BaseModel):
    product_id: UUID
    quantity: Decimal = Field(gt=0)


class AdjustmentItemIn(BaseModel):
    product_id: UUID
    quantity_delta: Decimal


class TransferIn(BaseModel):
    source_location_id: UUID
    destination_location_id: UUID
    items: list[MovementItemIn]
    comment: str | None = None
    operation_key: str | None = Field(default=None, min_length=8, max_length=120)


class StockAdjustmentIn(BaseModel):
    location_id: UUID
    items: list[AdjustmentItemIn]
    comment: str = Field(min_length=3, max_length=500)


class SaleIn(BaseModel):
    representative_location_id: UUID
    items: list[MovementItemIn]
    price_type: PriceType = PriceType.RETAIL
    comment: str | None = None
    operation_key: str | None = Field(default=None, min_length=8, max_length=120)


class CashHandoverIn(BaseModel):
    representative_location_id: UUID
    amount: Decimal = Field(gt=0)
    comment: str | None = None
    operation_key: str | None = Field(default=None, min_length=8, max_length=120)


class OperationOut(BaseModel):
    id: UUID
    message: str


class RepresentativeDebtOut(BaseModel):
    representative_location_id: UUID
    debt: Decimal


class RepresentativeDebtRow(BaseModel):
    representative_location_id: UUID
    representative_name: str
    debt: Decimal
