from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .integration_schemas import OneCSnapshot
from .models import Product, Representative, Warehouse
from .services import representative_balances, representative_debt, warehouse_balances


def build_1c_snapshot(session: Session) -> OneCSnapshot:
    representatives = session.scalars(select(Representative).order_by(Representative.name)).all()
    return OneCSnapshot(
        generated_at=datetime.now(UTC),
        warehouses=session.scalars(select(Warehouse).order_by(Warehouse.name)).all(),
        products=session.scalars(select(Product).order_by(Product.name)).all(),
        representatives=representatives,
        warehouse_balances=warehouse_balances(session),
        representative_balances=representative_balances(session),
        debts=[representative_debt(session, representative.id) for representative in representatives],
    )
