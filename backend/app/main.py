from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .account_security import router as account_security_router
from .admin_catalog import router as admin_catalog_router
from .admin_users import router as admin_users_router
from .api import router
from .audit import audit_mutations
from .bootstrap import ensure_bootstrap_admin
from .config import settings
from .database import SessionFactory, engine
from .integration_1c import router as integration_1c_router
from .integration_export_api import router as integration_export_router
from .reporting import router as reporting_router
from .system_status import router as system_status_router
from .unf_cloud import router as unf_cloud_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Структура БД обновляется только Alembic-миграциями до запуска приложения.
    await ensure_bootstrap_admin()
    yield
    await engine.dispose()


app = FastAPI(title=settings.app_name, version="0.13.0", lifespan=lifespan)
app.middleware("http")(audit_mutations)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(account_security_router)
app.include_router(reporting_router)
app.include_router(system_status_router)
app.include_router(integration_1c_router)
app.include_router(integration_export_router)
app.include_router(unf_cloud_router)
app.include_router(admin_users_router)
app.include_router(admin_catalog_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness: процесс FastAPI запущен и может отвечать на HTTP."""
    return {"status": "ok"}


@app.get("/health/ready")
async def readiness() -> dict[str, str]:
    """Readiness: backend видит PostgreSQL и таблицу версии Alembic."""
    try:
        async with SessionFactory() as session:
            await session.execute(text("SELECT 1"))
            revision = await session.scalar(text("SELECT version_num FROM alembic_version"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PostgreSQL недоступен",
        ) from exc

    if revision is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Версия схемы БД не определена",
        )

    return {
        "status": "ready",
        "database": "ok",
        "schema_revision": str(revision),
    }
