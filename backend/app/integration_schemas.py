from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from .document_schemas import DocumentRead
from .integration_models import OneCEntityType
from .money_schemas import MoneyPostingRead
from .schemas import (
    ProductRead,
    RepresentativeBalanceLine,
    RepresentativeDebt,
    RepresentativeRead,
    WarehouseBalanceLine,
    WarehouseRead,
)


class OneCEntityLinkWrite(BaseModel):
    entity_type: OneCEntityType
    backend_id: UUID
    external_ref: str = Field(min_length=1, max_length=255)

    @field_validator("external_ref")
    @classmethod
    def normalize_external_ref(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Ссылка 1С не может быть пустой")
        return normalized


class OneCEntityLinkRead(BaseModel):
    entity_type: OneCEntityType
    backend_id: UUID
    external_ref: str
    backend_code: str
    backend_name: str
    created_at: datetime
    updated_at: datetime


class OneCSnapshot(BaseModel):
    generated_at: datetime
    warehouses: list[WarehouseRead]
    products: list[ProductRead]
    representatives: list[RepresentativeRead]
    warehouse_balances: list[WarehouseBalanceLine]
    representative_balances: list[RepresentativeBalanceLine]
    debts: list[RepresentativeDebt]
    entity_links: list[OneCEntityLinkRead]


class OneCDocumentPage(BaseModel):
    items: list[DocumentRead]
    next_cursor: str | None = None
    has_more: bool


class OneCMoneyPostingPage(BaseModel):
    items: list[MoneyPostingRead]
    next_cursor: str | None = None
    has_more: bool
