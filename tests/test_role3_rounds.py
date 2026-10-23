
"""Run with python -m pytest -q tests/test_role3_rounds.py."""

import asyncio
from time import monotonic

import pytest

from coordinator.aggregation_adapter import AggregationResult, MockAggregationAdapter
from coordinator.round_manager import AggregationFailure, RoundManager


def run(coro):
    return asyncio.run(coro)


async def setup_round(client_ids, values, rejection=()):
    manager = RoundManager()
    started = await manager.start(30, set(client_ids))
    for cid, params in zip(client_ids, values):
        await manager.submit(
            client_id=cid,
            round_id=started["round_id"],
            model_version=started["model_version"],
            sample_count=10,
            parameters=params,
        )
    await manager.close()
    return manager, MockAggregationAdapter(rejection)


def test_success_updates_model_once():
    async def scenario():
        mgr, adapter = await setup_round(
            ["a", "b", "c"],
            [[1, 2, 3], [4, 5, 6], [7, 8, 9]],
        )
        assert (await mgr.current())["status"] == "awaiting_validation"
        result = await mgr.finalize(adapter)
        assert result["status"] == "completed"
        assert result["current_model_version"] == 1
        assert (await mgr.model())["parameters"] == [4, 5, 6]
        with pytest.raises(ValueError):
            await mgr.finalize(adapter)
        started = await mgr.start(30, {"a", "b", "c"})
        assert started["round_id"] == 2
        assert started["model_version"] == 1
    run(scenario())


def test_two_received_skip_without_model_change():
    async def scenario():
        mgr, _ = await setup_round(["a", "b"], [[1, 1, 1], [2, 2, 2]])
        assert (await mgr.current())["status"] == "skipped_insufficient_updates"
        assert (await mgr.model())["model_version"] == 0
        new = await mgr.start(30, {"a"})
        assert new["round_id"] == 2
        assert new["model_version"] == 0
    run(scenario())


def test_rejection_below_three_prevents_publication():
    async def scenario():
        mgr, adapter = await setup_round(
            ["a", "b", "c", "d"],
            [[1, 1, 1]] * 4,
            rejection={"c", "d"},
        )
        result = await mgr.finalize(adapter)
        assert result["status"] == "skipped_insufficient_updates"
        assert result["accepted_clients"] == ["a", "b"]
        assert result["rejected_clients"] == ["c", "d"]
        assert (await mgr.model()) == {"model_version": 0, "parameters": [0.0] * 3}
    run(scenario())


def test_failure_retains_model_and_allows_retry():
    class Failing:
        async def aggregate(self, **kwargs):
            raise RuntimeError("service unavailable")

    async def scenario():
        mgr, adapter = await setup_round(["a", "b", "c"], [[1, 1, 1]] * 3)
        with pytest.raises(AggregationFailure):
            await mgr.finalize(Failing())
        assert (await mgr.current())["status"] == "aggregation_failed"
        assert (await mgr.model())["model_version"] == 0
        assert (await mgr.finalize(adapter))["status"] == "completed"
    run(scenario())


def test_invalid_adapter_result_fails_closed():
    class Invalid:
        async def aggregate(self, **kwargs):
            return AggregationResult(["a", "b", "not-in-round"], [], [9, 9, 9])

    async def scenario():
        mgr, _ = await setup_round(["a", "b", "c"], [[1, 1, 1]] * 3)
        with pytest.raises(AggregationFailure):
            await mgr.finalize(Invalid())
        assert (await mgr.model())["model_version"] == 0
        assert (await mgr.current())["status"] == "aggregation_failed"
    run(scenario())


def test_concurrent_finalise_only_one_can_succeed():
    class SlowMock(MockAggregationAdapter):
        async def aggregate(self, **kwargs):
            await asyncio.sleep(0.02)
            return await super().aggregate(**kwargs)

    async def scenario():
        mgr, _ = await setup_round(["a", "b", "c"], [[2, 2, 2]] * 3)
        results = await asyncio.gather(
            mgr.finalize(SlowMock()), mgr.finalize(SlowMock()), return_exceptions=True
        )
        assert sum(isinstance(r, ValueError) for r in results) == 1
        assert sum(isinstance(r, dict) and r["status"] == "completed" for r in results) == 1
        assert (await mgr.model())["model_version"] == 1
    run(scenario())


def test_submission_rejects_invalid_model_shape():
    async def scenario():
        mgr = RoundManager()
        await mgr.start(30, {"a"})
        with pytest.raises(ValueError, match="parameter count"):
            await mgr.submit(client_id="a", round_id=1, model_version=0, sample_count=1, parameters=[1, 2])
    run(scenario())


def test_late_submission_rejected():
    async def scenario():
        mgr = RoundManager()
        await mgr.start(30, {"a"})
        mgr._deadline_clock = monotonic() - 1
        with pytest.raises(ValueError, match="no longer collecting"):
            await mgr.submit(client_id="a", round_id=1, model_version=0, sample_count=1, parameters=[1, 2, 3])
    run(scenario())
