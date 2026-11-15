import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.auth import router as auth_router
from app.api.v1.users import router as users_router
from app.core.config import settings
from app.core.migration_runner import run_auto_migrations
from app.core.redis_cluster import RedisClusterClient, init_redis_cluster
from app.core.session import AsyncSessionLocal, engine
from app.core.tantivy_search import (
    TantivyUserIndex,
    close_tantivy_user_index,
    init_tantivy_user_index,
)
from app.db.seeder import run_initial_seed
from app.workers.outbox_relay import OutboxRelayWorker

logging.basicConfig(level=settings.log_level.upper())
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    redis_client: RedisClusterClient | None = None
    search_index: TantivyUserIndex | None = None
    worker: OutboxRelayWorker | None = None
    try:
        await run_auto_migrations()
        redis_client = await init_redis_cluster()
        search_index = init_tantivy_user_index()
        async with AsyncSessionLocal() as session:
            await run_initial_seed(session, search_index)
        worker = OutboxRelayWorker(search_index)
        await worker.recover_and_flush_on_startup()
        worker.start()
        logger.info("Application startup complete; Tantivy outbox relay is active")
        yield
    finally:
        if worker is not None:
            await worker.stop()
        if search_index is not None:
            await close_tantivy_user_index()
        if redis_client is not None:
            await redis_client.aclose()
        await engine.dispose()


app = FastAPI(
    title="FastAPI Enterprise Architecture Blueprint",
    version="1.0.0",
    lifespan=lifespan,
)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")


@app.get("/health", tags=["Health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
