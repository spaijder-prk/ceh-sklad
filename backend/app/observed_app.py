from contextlib import asynccontextmanager

from .main import app
from .observability import install_observability
from .realtime import stock_updates


base_lifespan = app.router.lifespan_context


@asynccontextmanager
async def production_lifespan(application):
    async with base_lifespan(application):
        await stock_updates.start()
        try:
            yield
        finally:
            await stock_updates.stop()


app.router.lifespan_context = production_lifespan
install_observability(app)
