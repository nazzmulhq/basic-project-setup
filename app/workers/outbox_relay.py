import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.core.session import AsyncSessionLocal
from app.core.tantivy_search import SearchOperation, TantivyUserIndex
from app.models.outbox import OutboxEvent

logger = logging.getLogger(__name__)
BATCH_SIZE = 100
MAX_RETRIES = 10


class OutboxRelayWorker:
    def __init__(self, search_index: TantivyUserIndex, poll_interval: float = 2.0) -> None:
        self.search_index = search_index
        self.poll_interval = poll_interval
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def recover_and_flush_on_startup(self) -> None:
        now = datetime.now(UTC)
        stale_cutoff = now - timedelta(minutes=5)
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                update(OutboxEvent)
                .where(
                    (OutboxEvent.status == "FAILED")
                    | (
                        (OutboxEvent.status == "PROCESSING")
                        & (OutboxEvent.updated_at <= stale_cutoff)
                    )
                )
                .values(status="PENDING", next_retry_at=now)
            )
            await session.commit()
            if result.rowcount:
                logger.info("Recovered %s outbox events on startup", result.rowcount)

        while await self.process_batch():
            pass

    async def process_batch(self) -> int:
        now = datetime.now(UTC)
        async with AsyncSessionLocal() as session:
            statement = (
                select(OutboxEvent)
                .where(
                    OutboxEvent.status.in_(["PENDING", "FAILED"]),
                    OutboxEvent.next_retry_at <= now,
                )
                .order_by(OutboxEvent.created_at.asc())
                .limit(BATCH_SIZE)
                .with_for_update(skip_locked=True)
            )
            events = list((await session.execute(statement)).scalars().all())
            if not events:
                return 0

            try:
                operations: list[SearchOperation] = [
                    {
                        "event_type": event.event_type,
                        "aggregate_id": event.aggregate_id,
                        "search_index": event.search_index,
                        "payload": event.payload,
                    }
                    for event in events
                ]
                await self.search_index.apply_events(operations)

                for event in events:
                    event.status = "PUBLISHED"
                    event.last_error = None
                await session.commit()
                logger.info("Applied %d outbox events to Tantivy", len(events))
                return len(events)
            except Exception as exc:
                logger.exception("Tantivy outbox batch failed")
                for event in events:
                    self._schedule_retry(event, str(exc)[:450], now)
                await session.commit()
                return 0

    @staticmethod
    def _schedule_retry(event: OutboxEvent, error: str, now: datetime) -> None:
        event.retry_count += 1
        event.last_error = error
        if event.retry_count >= MAX_RETRIES:
            event.status = "DEAD_LETTER"
        else:
            event.status = "FAILED"
            event.next_retry_at = now + timedelta(seconds=min(300, 2**event.retry_count))

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                count = await self.process_batch()
                if count == BATCH_SIZE:
                    continue
            except Exception:
                logger.exception("Unexpected outbox relay worker failure")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_interval)
            except TimeoutError:
                pass

    def start(self) -> None:
        if self._task is not None:
            raise RuntimeError("Outbox relay worker is already running")
        self._task = asyncio.create_task(self._run(), name="outbox-relay")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            await self._task
            self._task = None
