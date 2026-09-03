from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class PriceType(str, Enum):
    RETAIL = "retail"
    WHOLESALE = "wholesale"


class ProductOut(BaseModel):
    id: UUID
    sku: str
    name: str
    unit_name: str
    retail_price: Decimal
    wholesale_price: Decimal

    model_config = {"from_attributes": True}


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


class TransferIn(BaseModel):
    source_location_id: UUID
    destination_location_id: UUID
    items: list[MovementItemIn]
    comment: str | None = None


class SaleIn(BaseModel):
    representative_location_id: UUID
    items: list[MovementItemIn]
    price_type: PriceType = PriceType.RETAIL
    comment: str | None = None


class CashHandoverIn(BaseModel):
    representative_location_id: UUID
    amount: Decimal = Field(gt=0)
    comment: str | None = None


class OperationOut(BaseModel):
    id: UUID
    message: str


class RepresentativeDebtOut(BaseModel):
    representative_location_id: UUID
    debt: Decimal
