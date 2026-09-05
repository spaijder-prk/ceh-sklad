from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.integration_models import OneCEntityType
from app.integration_schemas import OneCEntityLinkWrite
from app.integration_service import (
    build_1c_snapshot,
    resolve_1c_entity_link,
    upsert_1c_entity_link,
)
from app.models import Product, Representative, Warehouse
from app.services import ConflictError, NotFoundError


def test_1c_entity_links_are_persistent_resolvable_and_present_in_snapshot():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        warehouse = Warehouse(code="LINK-WH", name="Склад для связи")
        representative = Representative(code="LINK-REP", name="Представитель для связи")
        product = Product(
            sku="LINK-001",
            name="Товар для связи",
            unit="шт",
            retail_price=Decimal("100.00"),
            wholesale_price=Decimal("80.00"),
        )
        session.add_all([warehouse, representative, product])
        session.commit()

        warehouse_link = upsert_1c_entity_link(
            session,
            OneCEntityLinkWrite(
                entity_type=OneCEntityType.WAREHOUSE,
                backend_id=warehouse.id,
                external_ref="1c:warehouse:0001",
            ),
        )
        product_link = upsert_1c_entity_link(
            session,
            OneCEntityLinkWrite(
                entity_type=OneCEntityType.PRODUCT,
                backend_id=product.id,
                external_ref="1c:product:0001",
            ),
        )
        upsert_1c_entity_link(
            session,
            OneCEntityLinkWrite(
                entity_type=OneCEntityType.REPRESENTATIVE,
                backend_id=representative.id,
                external_ref="1c:representative:0001",
            ),
        )

        assert warehouse_link.backend_code == "LINK-WH"
        assert product_link.backend_code == "LINK-001"
        resolved = resolve_1c_entity_link(
            session,
            OneCEntityType.PRODUCT,
            "1c:product:0001",
        )
        assert resolved.backend_id == product.id
        assert resolved.backend_name == "Товар для связи"

        updated = upsert_1c_entity_link(
            session,
            OneCEntityLinkWrite(
                entity_type=OneCEntityType.WAREHOUSE,
                backend_id=warehouse.id,
                external_ref="1c:warehouse:0001-new",
            ),
        )
        assert updated.external_ref == "1c:warehouse:0001-new"
        with pytest.raises(NotFoundError):
            resolve_1c_entity_link(
                session,
                OneCEntityType.WAREHOUSE,
                "1c:warehouse:0001",
            )

        snapshot = build_1c_snapshot(session)
        assert len(snapshot.entity_links) == 3
        assert {
            (link.entity_type, link.external_ref)
            for link in snapshot.entity_links
        } == {
            (OneCEntityType.WAREHOUSE, "1c:warehouse:0001-new"),
            (OneCEntityType.PRODUCT, "1c:product:0001"),
            (OneCEntityType.REPRESENTATIVE, "1c:representative:0001"),
        }


def test_1c_entity_link_rejects_duplicate_reference_for_same_entity_type():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        first = Product(
            sku="DUP-001",
            name="Первый товар",
            unit="шт",
            retail_price=Decimal("10.00"),
            wholesale_price=Decimal("8.00"),
        )
        second = Product(
            sku="DUP-002",
            name="Второй товар",
            unit="шт",
            retail_price=Decimal("20.00"),
            wholesale_price=Decimal("16.00"),
        )
        session.add_all([first, second])
        session.commit()

        upsert_1c_entity_link(
            session,
            OneCEntityLinkWrite(
                entity_type=OneCEntityType.PRODUCT,
                backend_id=first.id,
                external_ref="1c:product:shared",
            ),
        )
        with pytest.raises(ConflictError):
            upsert_1c_entity_link(
                session,
                OneCEntityLinkWrite(
                    entity_type=OneCEntityType.PRODUCT,
                    backend_id=second.id,
                    external_ref="1c:product:shared",
                ),
            )


def test_1c_entity_link_rejects_unknown_backend_entity():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        with pytest.raises(NotFoundError):
            upsert_1c_entity_link(
                session,
                OneCEntityLinkWrite(
                    entity_type=OneCEntityType.WAREHOUSE,
                    backend_id=uuid4(),
                    external_ref="1c:warehouse:missing",
                ),
            )
