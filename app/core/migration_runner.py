import logging
from pathlib import Path

from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.core.config import settings

logger = logging.getLogger(__name__)
MIGRATION_LOCK_ID = 8844221100
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _upgrade_on_connection(connection) -> None:
    alembic_config = Config(str(PROJECT_ROOT / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    alembic_config.attributes["connection"] = connection
    command.upgrade(alembic_config, "head")


async def run_auto_migrations() -> None:
    migration_engine = create_async_engine(
        settings.direct_database_url,
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
    )
    try:
        async with migration_engine.connect() as connection:
            logger.info("Waiting for PostgreSQL migration advisory lock")
            await connection.execute(
                text("SELECT pg_advisory_lock(:lock_id)"),
                {"lock_id": MIGRATION_LOCK_ID},
            )
            try:
                await connection.run_sync(_upgrade_on_connection)
                logger.info("Database schema is current at Alembic head")
            finally:
                await connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": MIGRATION_LOCK_ID},
                )
    finally:
        await migration_engine.dispose()
