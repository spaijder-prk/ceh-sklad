from __future__ import annotations

import pytest_asyncio
from sqlalchemy import text

from app.database import SessionFactory


@pytest_asyncio.fixture(autouse=True)
async def clean_database():
    """Каждый интеграционный тест начинает работу с пустыми регистрами и справочниками."""
    async with SessionFactory() as session:
        await session.execute(
            text(
                "TRUNCATE TABLE money_transactions, stock_movements, stock_document_lines, "
                "stock_documents, inventory_balances, users, products, locations CASCADE"
            )
        )
        await session.commit()
    yield


@pytest_asyncio.fixture
async def session():
    async with SessionFactory() as db_session:
        yield db_session
        await db_session.rollback()
