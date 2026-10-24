
"""Deadline processing within a single coordinator process.

After a restart, main.py re-schedules the saved round using its UTC deadline.
"""

import asyncio
from datetime import datetime, timezone
import logging

from coordinator.round_manager import (
    AggregationFailure,
    RoundManager,
)

logger = logging.getLogger(__name__)


class DeadlineWorker:
    def __init__(
        self,
        manager: RoundManager,
        aggregator,
    ):
        self._manager = manager
        self._aggregator = aggregator
        self._tasks: set[asyncio.Task] = set()

    def schedule(
        self,
        round_id: int,
        delay_seconds: float,
    ):
        task = asyncio.create_task(
            self._run(round_id, delay_seconds)
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(
        self,
        round_id: int,
        delay_seconds: float,
    ):
        try:
            await asyncio.sleep(
                max(0, delay_seconds)
            )

            while True:
                info = await self._manager.current()

                if (
                    info is None
                    or info["round_id"] != round_id
                ):
                    return

                if info["status"] != "collecting":
                    break

                # Handle timers waking slightly before the deadline.
                remaining = (
                    datetime.fromisoformat(
                        info["deadline_at"]
                    )
                    - datetime.now(timezone.utc)
                ).total_seconds()

                await asyncio.sleep(
                    max(0.001, remaining)
                )

            if info["status"] == "deadline_reached":
                try:
                    await self._manager.close()
                except ValueError:
                    # Another request may have closed the round.
                    pass

            info = await self._manager.current()

            if (
                info is not None
                and info["round_id"] == round_id
                and info["status"] == "awaiting_validation"
                and self._aggregator is not None
            ):
                try:
                    await self._manager.finalize(
                        self._aggregator
                    )

                except ValueError:
                    # Another caller began finalisation.
                    pass

                except AggregationFailure:
                    logger.exception(
                        "Aggregation failed for round %s",
                        round_id,
                    )

        except asyncio.CancelledError:
            raise

        except Exception:
            logger.exception(
                "Deadline processing failed for round %s",
                round_id,
            )

    async def stop(self):
        pending = list(self._tasks)

        for task in pending:
            task.cancel()

        if pending:
            await asyncio.gather(
                *pending,
                return_exceptions=True,
            )
