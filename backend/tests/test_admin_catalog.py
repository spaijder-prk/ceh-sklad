from decimal import Decimal

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.auth import create_access_token, hash_password
from app.main import app
from app.models import InventoryBalance, Location, LocationKind, Product, User, UserRole


async def test_catalog_updates_and_safe_archiving(session):
    admin = User(
        name="Администратор каталога",
        login="admin-catalog",
        password_hash=hash_password("admin-password-123"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    representative_location = Location(name="Виртуальный склад", kind=LocationKind.REPRESENTATIVE)
    warehouse = Location(name="Рабочий склад", kind=LocationKind.WAREHOUSE)
    product = Product(
        sku="CAT-1",
        name="Исходный товар",
        unit_name="шт",
        retail_price=Decimal("100.00"),
        wholesale_price=Decimal("80.00"),
        is_active=True,
    )
    session.add_all([admin, representative_location, warehouse, product])
    await session.flush()
    representative = User(
        name="Активный представитель",
        login="catalog-rep",
        password_hash=hash_password("rep-password-123"),
        role=UserRole.REPRESENTATIVE,
        location_id=representative_location.id,
        is_active=True,
    )
    session.add(representative)
    session.add(InventoryBalance(location_id=warehouse.id, product_id=product.id, quantity=Decimal("2")))
    await session.commit()

    admin_id = admin.id
    representative_id = representative.id
    representative_location_id = representative_location.id
    warehouse_id = warehouse.id
    product_id = product.id
    headers = {"Authorization": f"Bearer {create_access_token(admin)}"}
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        edited = await client.patch(
            f"/api/v1/admin/catalog/products/{product_id}",
            json={"name": "Обновленный товар", "retail_price": "125.00", "wholesale_price": "95.00"},
            headers=headers,
        )
        product_archive_with_stock = await client.patch(
            f"/api/v1/admin/catalog/products/{product_id}",
            json={"is_active": False},
            headers=headers,
        )
        representative_archive = await client.patch(
            f"/api/v1/admin/catalog/locations/{representative_location_id}",
            json={"is_active": False},
            headers=headers,
        )

    assert edited.status_code == 200
    assert edited.json()["name"] == "Обновленный товар"
    assert edited.json()["retail_price"] == "125.00"
    assert product_archive_with_stock.status_code == 409
    assert representative_archive.status_code == 409

    balance = await session.scalar(
        select(InventoryBalance).where(
            InventoryBalance.location_id == warehouse_id,
            InventoryBalance.product_id == product_id,
        )
    )
    representative_row = await session.get(User, representative_id)
    assert balance is not None
    assert representative_row is not None
    balance.quantity = Decimal("0")
    representative_row.is_active = False
    await session.commit()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        product_archived = await client.patch(
            f"/api/v1/admin/catalog/products/{product_id}",
            json={"is_active": False},
            headers=headers,
        )
        location_renamed = await client.patch(
            f"/api/v1/admin/catalog/locations/{warehouse_id}",
            json={"name": "Переименованный склад", "is_active": False},
            headers=headers,
        )
        representative_archived = await client.patch(
            f"/api/v1/admin/catalog/locations/{representative_location_id}",
            json={"is_active": False},
            headers=headers,
        )
        active_products = await client.get("/api/v1/products", headers=headers)
        active_locations = await client.get("/api/v1/locations", headers=headers)

    assert product_archived.status_code == 200 and product_archived.json()["is_active"] is False
    assert location_renamed.status_code == 200 and location_renamed.json()["is_active"] is False
    assert representative_archived.status_code == 200 and representative_archived.json()["is_active"] is False
    assert all(row["id"] != str(product_id) for row in active_products.json())
    assert all(row["id"] not in {str(warehouse_id), str(representative_location_id)} for row in active_locations.json())

    # Текущий администратор остается активным, архивирование справочников не влияет на его доступ.
    admin_row = await session.get(User, admin_id)
    assert admin_row is not None and admin_row.is_active is True
