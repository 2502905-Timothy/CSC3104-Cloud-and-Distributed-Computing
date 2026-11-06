"""Role 3: registration is not evidence of an online, ready client."""

import asyncio

import pytest

from coordinator.round_manager import RoundManager


def test_client_readiness_heartbeat_and_expiry():
    async def scenario():
        manager = RoundManager()
        await manager.register("client-1")
        status = await manager.client_statuses()
        assert status["online_count"] == status["ready_count"] == 0
        assert status["clients"][0]["online"] is False

        await manager.heartbeat("client-1", dataset_ready=True, sample_count=781)
        status = await manager.client_statuses()
        assert status["online_count"] == status["ready_count"] == 1
        assert status["clients"][0]["sample_count"] == 781
        assert status["clients"][0]["dataset_ready"] is True

        # Don't wait for real time to pass in tests.
        manager._client_presence["client-1"]["seen_monotonic"] -= 31
        status = await manager.client_statuses()
        assert status["online_count"] == status["ready_count"] == 0
        assert status["clients"][0]["sample_count"] == 0
        assert status["clients"][0]["last_seen_at"] is not None

    asyncio.run(scenario())


def test_not_ready_validation_and_unknown_client():
    async def scenario():
        manager = RoundManager()
        await manager.register("client-1")
        with pytest.raises(ValueError, match="not registered"):
            await manager.heartbeat("client-2", dataset_ready=True, sample_count=10)
        with pytest.raises(ValueError, match="at least one"):
            await manager.heartbeat("client-1", dataset_ready=True, sample_count=0)
        with pytest.raises(ValueError, match="negative"):
            await manager.heartbeat("client-1", dataset_ready=False, sample_count=-1)
        await manager.heartbeat("client-1", dataset_ready=False, sample_count=10)
        status = await manager.client_statuses()
        assert status["online_count"] == 1
        assert status["ready_count"] == 0
        assert status["clients"][0]["sample_count"] == 10

    asyncio.run(scenario())


def test_registration_persists_but_online_status_does_not(tmp_path):
    async def scenario():
        db_path = str(tmp_path / "readiness.sqlite3")
        first = RoundManager(db_path=db_path)
        await first.register("client-1")
        await first.heartbeat("client-1", dataset_ready=True, sample_count=99)
        restored = RoundManager(db_path=db_path)
        assert (await restored.clients())["clients"] == ["client-1"]
        status = await restored.client_statuses()
        assert status["online_count"] == status["ready_count"] == 0
        assert status["clients"][0]["last_seen_at"] is None

    asyncio.run(scenario())
