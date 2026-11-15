from collections.abc import Mapping
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.session import DBSessionDeps
from app.models.outbox import OutboxEvent


class OutboxRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def stage_event(
        self,
        *,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        search_index: str,
        payload: Mapping[str, Any],
    ) -> OutboxEvent:
        event = OutboxEvent(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            search_index=search_index,
            payload=dict(payload),
        )
        self.db.add(event)
        return event


def get_outbox_repository(db: DBSessionDeps) -> OutboxRepository:
    return OutboxRepository(db)


OutboxRepositoryDeps = Annotated[OutboxRepository, Depends(get_outbox_repository)]
