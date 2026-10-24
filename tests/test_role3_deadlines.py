
"""Automated tests for coordinator deadline processing."""

import asyncio

from coordinator.aggregation_adapter import (
    MockAggregationAdapter,
)
from coordinator.deadline_worker import DeadlineWorker
from coordinator.round_manager import RoundManager


async def prepare_updates(manager, info, names):
    for name in names:
        await manager.submit(
            client_id=name,
            round_id=info["round_id"],
            model_version=info["model_version"],
            sample_count=2,
            parameters=[2.0, 2.0, 2.0],
        )


def test_three_updates_auto_finalize():
    async def scenario():
        manager = RoundManager()
        worker = DeadlineWorker(
            manager,
            MockAggregationAdapter(),
        )

        try:
            info = await manager.start(
                1, {"a", "b", "c"}
            )

            worker.schedule(info["round_id"], 1)

            await prepare_updates(
                manager, info, ("a", "b", "c")
            )

            await asyncio.sleep(1.10)

            assert (
                await manager.current()
            )["status"] == "completed"

            assert (
                await manager.model()
            )["model_version"] == 1

        finally:
            await worker.stop()

    asyncio.run(scenario())


def test_two_updates_are_skipped_at_deadline():
    async def scenario():
        manager = RoundManager()
        worker = DeadlineWorker(
            manager,
            MockAggregationAdapter(),
        )

        try:
            info = await manager.start(
                1, {"a", "b", "c"}
            )

            worker.schedule(info["round_id"], 1)

            await prepare_updates(
                manager, info, ("a", "b")
            )

            await asyncio.sleep(1.10)

            assert (
                await manager.current()
            )["status"] == "skipped_insufficient_updates"

            assert (
                await manager.model()
            )["model_version"] == 0

        finally:
            await worker.stop()

    asyncio.run(scenario())


def test_rejected_update_does_not_publish_model():
    async def scenario():
        manager = RoundManager()

        worker = DeadlineWorker(
            manager,
            MockAggregationAdapter(["c"]),
        )

        try:
            info = await manager.start(
                1, {"a", "b", "c"}
            )

            worker.schedule(info["round_id"], 1)

            await prepare_updates(
                manager, info, ("a", "b", "c")
            )

            await asyncio.sleep(1.10)

            state = await manager.current()

            assert (
                state["status"]
                == "skipped_insufficient_updates"
            )

            assert state["rejected_clients"] == ["c"]

            assert (
                await manager.model()
            )["model_version"] == 0

        finally:
            await worker.stop()

    asyncio.run(scenario())
