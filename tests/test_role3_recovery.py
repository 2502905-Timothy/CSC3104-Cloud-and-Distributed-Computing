
"""SQLite durability and restart tests for TrustFed Role 3."""

import asyncio

import pytest

from coordinator.aggregation_adapter import (
    MockAggregationAdapter,
)
from coordinator.deadline_worker import DeadlineWorker
from coordinator.round_manager import RoundManager


def test_registration_and_pending_updates_survive_restart(tmp_path):
    async def scenario():
        db = str(tmp_path / "state.sqlite3")

        before = RoundManager(db_path=db)

        await before.register("a")
        await before.register("b")
        await before.register("c")

        info = await before.start(60)

        await before.submit(
            client_id="a",
            round_id=1,
            model_version=0,
            sample_count=4,
            parameters=[1.0, 2.0, 3.0],
        )

        after = RoundManager(db_path=db)

        assert (await after.clients())["count"] == 3

        state = await after.current()

        assert state["round_id"] == info["round_id"]
        assert state["submitted_clients"] == ["a"]
        assert state["status"] == "collecting"

        with pytest.raises(
            ValueError,
            match="already submitted",
        ):
            await after.submit(
                client_id="a",
                round_id=1,
                model_version=0,
                sample_count=4,
                parameters=[1, 2, 3],
            )

    asyncio.run(scenario())


def test_published_model_and_round_number_survive_restart(tmp_path):
    async def scenario():
        db = str(tmp_path / "state.sqlite3")

        first = RoundManager(db_path=db)
        await first.start(60, {"a", "b", "c"})

        for client, value in (
            ("a", 1),
            ("b", 2),
            ("c", 3),
        ):
            await first.submit(
                client_id=client,
                round_id=1,
                model_version=0,
                sample_count=10,
                parameters=[value] * 3,
            )

        await first.close()
        await first.finalize(
            MockAggregationAdapter()
        )

        recovered = RoundManager(db_path=db)

        assert (await recovered.model()) == {
            "model_version": 1,
            "parameters": [2.0] * 3,
        }

        assert (
            await recovered.current()
        )["status"] == "completed"

        next_round = await recovered.start(
            60, {"a", "b", "c"}
        )

        assert (
            next_round["round_id"],
            next_round["model_version"],
        ) == (2, 1)

    asyncio.run(scenario())


def test_skipped_round_persists_without_changing_version(tmp_path):
    async def scenario():
        db = str(tmp_path / "state.sqlite3")

        first = RoundManager(db_path=db)
        await first.start(60, {"a", "b"})

        for name in ("a", "b"):
            await first.submit(
                client_id=name,
                round_id=1,
                model_version=0,
                sample_count=1,
                parameters=[1.0] * 3,
            )

        await first.close()

        recovered = RoundManager(db_path=db)

        assert (
            await recovered.current()
        )["status"] == "skipped_insufficient_updates"

        assert (
            await recovered.model()
        )["model_version"] == 0

        assert (
            await recovered.start(10, {"a"})
        )["round_id"] == 2

    asyncio.run(scenario())


def test_expired_round_is_processed_after_restart(tmp_path):
    async def scenario():
        db = str(tmp_path / "state.sqlite3")

        first = RoundManager(db_path=db)

        info = await first.start(
            1, {"a", "b", "c", "d"}
        )

        for name in ("a", "b", "c"):
            await first.submit(
                client_id=name,
                round_id=1,
                model_version=0,
                sample_count=2,
                parameters=[2.0] * 3,
            )

        # Simulate downtime longer than the round deadline.
        await asyncio.sleep(1.05)

        resumed = RoundManager(db_path=db)

        worker = DeadlineWorker(
            resumed,
            MockAggregationAdapter(),
        )

        try:
            worker.schedule(
                info["round_id"], 0
            )

            await asyncio.sleep(0.05)

            assert (
                await resumed.current()
            )["status"] == "completed"

            assert (
                await resumed.model()
            )["model_version"] == 1

        finally:
            await worker.stop()

    asyncio.run(scenario())


def test_interrupted_aggregation_does_not_publish_model(tmp_path):
    class PausedAggregator:
        def __init__(self):
            self.started = asyncio.Event()

        async def aggregate(self, **kwargs):
            self.started.set()
            await asyncio.Event().wait()

    async def scenario():
        db = str(tmp_path / "state.sqlite3")

        first = RoundManager(db_path=db)
        await first.start(
            60, {"a", "b", "c"}
        )

        for name in ("a", "b", "c"):
            await first.submit(
                client_id=name,
                round_id=1,
                model_version=0,
                sample_count=2,
                parameters=[2.0] * 3,
            )

        await first.close()

        paused = PausedAggregator()

        job = asyncio.create_task(
            first.finalize(paused)
        )

        await paused.started.wait()

        # Simulate recovering a saved in-progress round.
        # Do not operate two managers simultaneously in deployment.
        recovered = RoundManager(db_path=db)

        assert (
            await recovered.current()
        )["status"] == "aggregation_failed"

        assert (
            await recovered.model()
        )["model_version"] == 0

        job.cancel()

        await asyncio.gather(
            job,
            return_exceptions=True,
        )

        result = await recovered.finalize(
            MockAggregationAdapter()
        )

        assert result["status"] == "completed"

        assert (
            await recovered.model()
        )["model_version"] == 1

    asyncio.run(scenario())
