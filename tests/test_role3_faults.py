
"""Final Role 3 concurrency and fault-injection regression tests.

Run: python -m pytest -q tests/test_role3_faults.py
No production coordinator files need changing for this milestone.
"""

import asyncio
import sqlite3

import pytest

from coordinator.aggregation_adapter import AggregationResult, MockAggregationAdapter
from coordinator.deadline_worker import DeadlineWorker
from coordinator.round_manager import AggregationFailure, RoundManager


def run(coroutine):
    return asyncio.run(coroutine)


async def ready_round(manager, clients=("a", "b", "c")):
    """Start a full mock round and close it for finalisation."""
    info = await manager.start(60, set(clients))

    for index, client in enumerate(clients, 1):
        await manager.submit(
            client_id=client,
            round_id=info["round_id"],
            model_version=info["model_version"],
            sample_count=10,
            parameters=[float(index)] * 3,
        )

    assert (await manager.close())["status"] == "awaiting_validation"
    return info


def test_parallel_distinct_submissions_are_all_preserved(tmp_path):
    async def scenario():
        db = str(tmp_path / "parallel.sqlite3")
        manager = RoundManager(db_path=db)
        clients = {f"client-{index}" for index in range(40)}
        info = await manager.start(60, clients)

        async def submit(client):
            return await manager.submit(
                client_id=client,
                round_id=info["round_id"],
                model_version=info["model_version"],
                sample_count=1,
                parameters=[1.0, 2.0, 3.0],
            )

        responses = await asyncio.gather(
            *(submit(name) for name in clients)
        )

        assert len(responses) == 40
        assert all(
            r["status"] == "received_unvalidated"
            for r in responses
        )

        state = await manager.current()
        assert state["submissions_received"] == 40

        recovered = RoundManager(db_path=db)
        assert (
            await recovered.current()
        )["submitted_clients"] == sorted(clients)

    run(scenario())


def test_duplicate_submissions_have_exactly_one_winner(tmp_path):
    async def scenario():
        manager = RoundManager(
            db_path=str(tmp_path / "duplicates.sqlite3")
        )
        info = await manager.start(60, {"a"})

        async def submit_once():
            return await manager.submit(
                client_id="a",
                round_id=info["round_id"],
                model_version=0,
                sample_count=1,
                parameters=[1.0] * 3,
            )

        results = await asyncio.gather(
            *(submit_once() for _ in range(25)),
            return_exceptions=True,
        )

        assert sum(
            isinstance(r, dict) for r in results
        ) == 1

        assert sum(
            isinstance(r, ValueError) for r in results
        ) == 24

        assert (
            await manager.current()
        )["submissions_received"] == 1

    run(scenario())


def test_parallel_duplicate_registration_is_idempotent_in_state(tmp_path):
    async def scenario():
        db = str(tmp_path / "registration.sqlite3")
        manager = RoundManager(db_path=db)

        results = await asyncio.gather(
            *(manager.register("same-client") for _ in range(20)),
            return_exceptions=True,
        )

        assert sum(
            isinstance(r, dict) for r in results
        ) == 1

        assert sum(
            isinstance(r, ValueError) for r in results
        ) == 19

        recovered = RoundManager(db_path=db)

        assert (
            await recovered.clients()
        )["clients"] == ["same-client"]

    run(scenario())


def test_concurrent_finalisers_publish_only_once(tmp_path):
    class SlowAggregator(MockAggregationAdapter):
        async def aggregate(self, **kwargs):
            await asyncio.sleep(0.02)
            return await super().aggregate(**kwargs)

    async def scenario():
        db = str(tmp_path / "finalise.sqlite3")
        manager = RoundManager(db_path=db)

        await ready_round(manager)

        results = await asyncio.gather(
            manager.finalize(SlowAggregator()),
            manager.finalize(SlowAggregator()),
            return_exceptions=True,
        )

        assert sum(
            isinstance(r, dict)
            and r["status"] == "completed"
            for r in results
        ) == 1

        assert sum(
            isinstance(r, ValueError)
            for r in results
        ) == 1

        assert (
            await manager.model()
        )["model_version"] == 1

        recovered = RoundManager(db_path=db)

        assert (
            await recovered.model()
        )["model_version"] == 1

    run(scenario())


def test_old_model_remains_visible_until_aggregation_commits(tmp_path):
    class PausingAggregator(MockAggregationAdapter):
        def __init__(self):
            super().__init__()
            self.entered = asyncio.Event()
            self.release = asyncio.Event()

        async def aggregate(self, **kwargs):
            self.entered.set()
            await self.release.wait()
            return await super().aggregate(**kwargs)

    async def scenario():
        manager = RoundManager(
            db_path=str(tmp_path / "publish.sqlite3")
        )
        await ready_round(manager)

        adapter = PausingAggregator()
        task = asyncio.create_task(
            manager.finalize(adapter)
        )

        try:
            await asyncio.wait_for(
                adapter.entered.wait(),
                timeout=2,
            )

            assert (
                await manager.current()
            )["status"] == "aggregating"

            assert await manager.model() == {
                "model_version": 0,
                "parameters": [0.0] * 3,
            }

            with pytest.raises(
                ValueError,
                match="already exists",
            ):
                await manager.start(
                    60,
                    {"a", "b", "c"},
                )

            adapter.release.set()

            result = await asyncio.wait_for(
                task,
                timeout=2,
            )

            assert result["status"] == "completed"

            assert await manager.model() == {
                "model_version": 1,
                "parameters": [2.0] * 3,
            }

        finally:
            adapter.release.set()
            await asyncio.gather(
                task,
                return_exceptions=True,
            )

    run(scenario())


def test_adapter_exception_preserves_model_across_restart(tmp_path):
    class BrokenAggregator:
        async def aggregate(self, **kwargs):
            raise ConnectionError(
                "aggregation service unavailable"
            )

    async def scenario():
        db = str(tmp_path / "adapter_failure.sqlite3")
        manager = RoundManager(db_path=db)

        await ready_round(manager)

        with pytest.raises(AggregationFailure):
            await manager.finalize(
                BrokenAggregator()
            )

        assert (
            await manager.current()
        )["status"] == "aggregation_failed"

        assert (
            await manager.model()
        )["model_version"] == 0

        recovered = RoundManager(db_path=db)

        assert (
            await recovered.current()
        )["status"] == "aggregation_failed"

        assert (
            await recovered.model()
        )["model_version"] == 0

        result = await recovered.finalize(
            MockAggregationAdapter()
        )

        assert result["status"] == "completed"

        another_restart = RoundManager(db_path=db)

        assert (
            await another_restart.model()
        )["model_version"] == 1

    run(scenario())


def test_invalid_aggregation_client_ids_fail_closed(tmp_path):
    class InvalidAggregator:
        async def aggregate(self, **kwargs):
            return AggregationResult(
                accepted_clients=[
                    "a",
                    "b",
                    "unknown",
                ],
                rejected_clients=[],
                parameters=[9.0, 9.0, 9.0],
            )

    async def scenario():
        db = str(tmp_path / "invalid_result.sqlite3")
        manager = RoundManager(db_path=db)

        await ready_round(manager)

        with pytest.raises(AggregationFailure):
            await manager.finalize(
                InvalidAggregator()
            )

        recovered = RoundManager(db_path=db)

        assert await recovered.model() == {
            "model_version": 0,
            "parameters": [0.0] * 3,
        }

        assert (
            await recovered.current()
        )["status"] == "aggregation_failed"

    run(scenario())


def test_failed_database_write_does_not_acknowledge_update(tmp_path):
    async def scenario():
        db = str(tmp_path / "write_failure.sqlite3")
        manager = RoundManager(db_path=db)

        info = await manager.start(60, {"a"})

        original_save = manager._store.save

        def disk_unavailable(_state):
            raise sqlite3.OperationalError(
                "simulated disk write failure"
            )

        manager._store.save = disk_unavailable

        try:
            with pytest.raises(
                sqlite3.OperationalError,
                match="simulated",
            ):
                await manager.submit(
                    client_id="a",
                    round_id=info["round_id"],
                    model_version=0,
                    sample_count=1,
                    parameters=[1.0] * 3,
                )

        finally:
            manager._store.save = original_save

        assert (
            await manager.current()
        )["submissions_received"] == 0

        recovered = RoundManager(db_path=db)

        assert (
            await recovered.current()
        )["submissions_received"] == 0

    run(scenario())


def test_expired_update_is_rejected_after_restart(tmp_path):
    async def scenario():
        db = str(tmp_path / "late.sqlite3")
        manager = RoundManager(db_path=db)

        info = await manager.start(
            1,
            {"a", "b", "c"},
        )

        await asyncio.sleep(1.05)

        restarted = RoundManager(db_path=db)

        with pytest.raises(
            ValueError,
            match="no longer collecting",
        ):
            await restarted.submit(
                client_id="a",
                round_id=info["round_id"],
                model_version=info["model_version"],
                sample_count=1,
                parameters=[1.0] * 3,
            )

        worker = DeadlineWorker(
            restarted,
            MockAggregationAdapter(),
        )

        try:
            worker.schedule(info["round_id"], 0)

            await asyncio.sleep(0.05)

            assert (
                await restarted.current()
            )["status"] == "skipped_insufficient_updates"

            assert (
                await restarted.model()
            )["model_version"] == 0

        finally:
            await worker.stop()

    run(scenario())


def test_old_model_version_is_rejected_after_recovery(tmp_path):
    async def scenario():
        db = str(tmp_path / "stale.sqlite3")
        manager = RoundManager(db_path=db)

        await ready_round(manager)
        await manager.finalize(
            MockAggregationAdapter()
        )

        recovered = RoundManager(db_path=db)

        info = await recovered.start(
            60,
            {"a"},
        )

        assert info["model_version"] == 1

        with pytest.raises(
            ValueError,
            match="incorrect model version",
        ):
            await recovered.submit(
                client_id="a",
                round_id=info["round_id"],
                model_version=0,
                sample_count=1,
                parameters=[1.0] * 3,
            )

        assert (
            await recovered.current()
        )["submissions_received"] == 0

    run(scenario())
