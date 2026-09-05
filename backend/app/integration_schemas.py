from datetime import datetime

from pydantic import BaseModel

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
