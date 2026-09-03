from datetime import UTC, datetime, timedelta
from decimal import Decimal

from httpx import ASGITransport, AsyncClient

from app.auth import create_access_token, hash_password
from app.config import settings
from app.main import app
from app.models import (
    IntegrationExchangeLog,
    Location,
    LocationKind,
    MoneyTransaction,
    MoneyTransactionKind,
    Product,
    StockDocument,
    StockDocumentKind,
    User,
    UserRole,
)


async def test_system_status_reports_operational_counters_and_checks_role(session, monkeypatch):
    monkeypatch.setattr(settings, "integration_1c_api_key", "test-status-1c-key")
    warehouse = Location(name="Склад статуса", kind=LocationKind.WAREHOUSE)
    representative = Location(name="Представитель статуса", kind=LocationKind.REPRESENTATIVE)
    product = Product(
        sku="STATUS-1",
        name="Товар статуса",
        unit_name="шт",
        retail_price=Decimal("10.00"),
        wholesale_price=Decimal("8.00"),
    )
    admin = User(
        name="Администратор статуса",
        login="status-admin",
        password_hash=hash_password("StatusAdmin123"),
        role=UserRole.ADMIN,
        login_locked_until=datetime.now(UTC) + timedelta(minutes=2),
    )
    manager = User(
        name="Руководитель статуса",
        login="status-manager",
        password_hash=hash_password("StatusManager123"),
        role=UserRole.MANAGER,
    )
    rep_user = User(
        name="Полевой пользователь статуса",
        login="status-rep",
        password_hash=hash_password("StatusRep123"),
        role=UserRole.REPRESENTATIVE,
        location=representative,
    )
    session.add_all([warehouse, representative, product, admin, manager, rep_user])
    await session.flush()

    document = StockDocument(kind=StockDocumentKind.TRANSFER, comment="Ожидает 1С")
    cash = MoneyTransaction(
        representative_location_id=representative.id,
        kind=MoneyTransactionKind.CASH_HANDOVER,
        amount=Decimal("-10.00"),
        comment="Ожидает 1С",
    )
    failed = IntegrationExchangeLog(
        direction="inbound",
        operation_key="status-failed-0001",
        entity_type="product",
        payload_hash="0" * 64,
        status="failed",
        payload={},
        error_message="Тестовая ошибка",
    )
    session.add_all([document, cash, failed])
    await session.commit()

    admin_token = create_access_token(admin)
    manager_token = create_access_token(manager)
    rep_token = create_access_token(rep_user)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        admin_response = await client.get(
            "/api/v1/system/status",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        manager_response = await client.get(
            "/api/v1/system/status",
            headers={"Authorization": f"Bearer {manager_token}"},
        )
        representative_response = await client.get(
            "/api/v1/system/status",
            headers={"Authorization": f"Bearer {rep_token}"},
        )

    assert admin_response.status_code == 200
    body = admin_response.json()
    assert body["schema_revision"] == "20260903_08"
    assert body["integration_1c_configured"] is True
    assert body["pending_1c_stock_documents"] == 1
    assert body["pending_1c_cash_handovers"] == 1
    assert body["failed_1c_last_24h"] == 1
    assert body["temporarily_locked_users"] == 1
    assert body["active_products"] == 1
    assert body["active_warehouses"] == 1
    assert body["active_representatives"] == 1
    assert body["oldest_pending_1c_at"] is not None
    assert body["unf_unmapped_products"] == 1
    assert body["unf_unmapped_warehouses"] == 1
    assert body["unf_unmapped_representatives"] == 1
    assert body["unf_mapping_ready"] is False
    assert manager_response.status_code == 200
    assert representative_response.status_code == 403


async def test_system_status_marks_unf_mapping_ready_when_all_active_objects_are_mapped(session, monkeypatch):
    monkeypatch.setattr(settings, "integration_1c_api_key", "test-status-1c-key")
    warehouse = Location(
        name="Склад УНФ готов",
        kind=LocationKind.WAREHOUSE,
        external_1c_id="unf-warehouse-ready",
    )
    representative = Location(
        name="Представитель УНФ готов",
        kind=LocationKind.REPRESENTATIVE,
        external_1c_id="unf-representative-ready",
    )
    product = Product(
        sku="UNF-READY",
        name="Товар УНФ готов",
        unit_name="шт",
        retail_price=Decimal("15.00"),
        wholesale_price=Decimal("12.00"),
        external_1c_id="unf-product-ready",
    )
    manager = User(
        name="Руководитель УНФ",
        login="unf-ready-manager",
        password_hash=hash_password("UnfReadyManager123"),
        role=UserRole.MANAGER,
    )
    session.add_all([warehouse, representative, product, manager])
    await session.commit()

    token = create_access_token(manager)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/system/status",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["unf_unmapped_products"] == 0
    assert body["unf_unmapped_warehouses"] == 0
    assert body["unf_unmapped_representatives"] == 0
    assert body["unf_mapping_ready"] is True
