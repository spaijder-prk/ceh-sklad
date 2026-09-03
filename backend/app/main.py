from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router
from .audit import audit_mutations
from .bootstrap import ensure_bootstrap_admin
from .config import settings
from .database import engine
from .integration_1c import router as integration_1c_router
from .reporting import router as reporting_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Структура БД обновляется только Alembic-миграциями до запуска приложения.
    await ensure_bootstrap_admin()
    yield
    await engine.dispose()


app = FastAPI(title=settings.app_name, version="0.6.0", lifespan=lifespan)
app.middleware("http")(audit_mutations)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(reporting_router)
app.include_router(integration_1c_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
