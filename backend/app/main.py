from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router
from .bootstrap import ensure_bootstrap_admin
from .config import settings
from .database import engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Структура БД обновляется только Alembic-миграциями до запуска приложения.
    await ensure_bootstrap_admin()
    yield
    await engine.dispose()


app = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
