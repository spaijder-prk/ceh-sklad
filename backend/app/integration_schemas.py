from datetime import datetime

from pydantic import BaseModel

from .document_schemas import DocumentRead
from .money_schemas import MoneyPostingRead
from .schemas import (
    ProductRead,
    RepresentativeBalanceLine,
    RepresentativeDebt,
    RepresentativeRead,
    WarehouseBalanceLine,
    WarehouseRead,
)


class OneCSnapshot(BaseModel):
    generated_at: datetime
    warehouses: list[WarehouseRead]
    products: list[ProductRead]
    representatives: list[RepresentativeRead]
    warehouse_balances: list[WarehouseBalanceLine]
    representative_balances: list[RepresentativeBalanceLine]
    debts: list[RepresentativeDebt]


class OneCDocumentPage(BaseModel):
    items: list[DocumentRead]
    next_cursor: str | None = None
    has_more: bool


class OneCMoneyPostingPage(BaseModel):
    items: list[MoneyPostingRead]
    next_cursor: str | None = None
    has_more: bool
