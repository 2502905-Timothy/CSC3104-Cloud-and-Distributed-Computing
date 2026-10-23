
"""Automatic deadline processing for the TrustFed coordinator.

This worker operates inside one Python process.
It does not provide restart-safe scheduling or
coordination across multiple server replicas.
"""

import asyncio
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
        deadline_seconds: int,
    ):
        """Schedule automatic processing for a round."""

        task = asyncio.create_task(
            self._run(round_id, deadline_seconds)
        )

        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(
        self,
        round_id: int,
        deadline_seconds: int,
    ):
        try:
            # Wait without blocking other client requests.
            await asyncio.sleep(deadline_seconds)

            info = await self._manager.current()

            # The round may already have been replaced.
            if (
                info is None
                or info["round_id"] != round_id
            ):
                return

            # Close collection if the round is still open.
            if info["status"] in {
                "collecting",
                "deadline_reached",
            }:
                try:
                    await self._manager.close()
                except ValueError:
                    # Another request may have closed it.
                    pass

            info = await self._manager.current()

            # Validate and aggregate only if appropriate.
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
                    # Another request may have started
                    # finalisation already.
                    pass

                except AggregationFailure:
                    # The previous model remains unchanged.
                    # A manual retry can be attempted.
                    logger.exception(
                        "Automatic aggregation failed "
                        "for round %s",
                        round_id,
                    )

        except asyncio.CancelledError:
            raise

        except Exception:
            logger.exception(
                "Automatic deadline handling failed "
                "for round %s",
                round_id,
            )

    async def stop(self):
        """Cancel pending tasks during server shutdown."""

        pending = list(self._tasks)

        for task in pending:
            task.cancel()

        if pending:
            await asyncio.gather(
                *pending,
                return_exceptions=True,
            )
