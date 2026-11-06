"""Stage 3: five successful rounds, skipped attempts, SQLite recovery, GUI."""

import asyncio
from types import SimpleNamespace

from coordinator.aggregation_adapter import MockAggregationAdapter
from coordinator.round_manager import RoundManager
import visualization.app as gui


def test_initial_progress_is_zero():
    async def scenario():
        progress = await RoundManager().training_progress()
        assert progress == {
            "target_successful_rounds": 5,
            "successful_rounds": 0,
            "attempted_rounds": 0,
            "skipped_rounds": 0,
            "round_in_progress": False,
            "current_round_status": None,
            "remaining_successful_rounds": 5,
            "ready_for_evaluation": False,
        }
    asyncio.run(scenario())


def test_skipped_attempt_does_not_count_and_five_successes_survive_restart(tmp_path):
    async def scenario():
        db = str(tmp_path / "progress.sqlite3")
        mgr = RoundManager(db_path=db)
        await mgr.start(30, {"a", "b"})
        for client_id in ("a", "b"):
            await mgr.submit(client_id=client_id, round_id=1, model_version=0,
                             sample_count=1, parameters=[1.0] * 3)
        result = await mgr.close()
        assert result["status"] == "skipped_insufficient_updates"
        assert (await mgr.training_progress())["skipped_rounds"] == 1
        for success in range(1, 6):
            started = await mgr.start(30, {"a", "b", "c"})
            for client_id in ("a", "b", "c"):
                await mgr.submit(client_id=client_id,
                                 round_id=started["round_id"],
                                 model_version=started["model_version"],
                                 sample_count=1, parameters=[float(success)] * 3)
            await mgr.close()
            await mgr.finalize(MockAggregationAdapter())
            assert (await mgr.training_progress())["successful_rounds"] == success

        progress = await RoundManager(db_path=db).training_progress()
        assert progress["successful_rounds"] == 5
        assert progress["attempted_rounds"] == 6
        assert progress["skipped_rounds"] == 1
        assert progress["remaining_successful_rounds"] == 0
        assert progress["ready_for_evaluation"] is True
    asyncio.run(scenario())


def test_active_round_not_mistaken_for_skipped_round():
    async def scenario():
        mgr = RoundManager()
        await mgr.start(30, {"a", "b", "c"})
        progress = await mgr.training_progress()
        assert progress["attempted_rounds"] == 1
        assert progress["skipped_rounds"] == 0
        assert progress["round_in_progress"] is True
        assert progress["ready_for_evaluation"] is False
    asyncio.run(scenario())


def test_round_progress_coordinator_api(monkeypatch):
    import coordinator.main as coordinator_api

    async def scenario():
        mgr = RoundManager()
        monkeypatch.setattr(coordinator_api, "round_manager", mgr)
        endpoint = next(route.endpoint for route in coordinator_api.app.routes
                        if getattr(route, "path", None) == "/rounds/progress")
        assert (await endpoint())["target_successful_rounds"] == 5
    asyncio.run(scenario())


def test_gui_forwards_round_progress(monkeypatch):
    async def scenario():
        called = []
        payloads = {
            "/health": (200, {"aggregation_mode": "none"}),
            "/clients": (200, {"clients": []}),
            "/rounds/current": (404, {}),
            "/model/current": (200, {"model_version": 0, "parameters": [0.0]}),
            "/clients/status": (200, {"clients": [], "ready_count": 0}),
            "/rounds/progress": (200, {"target_successful_rounds": 5,
                                        "successful_rounds": 1, "skipped_rounds": 2,
                                        "ready_for_evaluation": False}),
        }

        def fake_request(method, url, **kwargs):
            path = url.removeprefix("http://coordinator:8000")
            called.append(path)
            code, payload = payloads[path]
            return SimpleNamespace(status_code=code, ok=code < 400,
                                   json=lambda: payload)

        monkeypatch.setattr(gui, "api_request", fake_request)
        app = gui.build_app("coordinator", "http://coordinator:8000")
        endpoint = next(route.endpoint for route in app.routes
                        if getattr(route, "path", None) == "/api/status")
        result = await endpoint()
        assert result["training_progress"]["successful_rounds"] == 1
        assert "/rounds/progress" in called
    asyncio.run(scenario())


def test_gui_backward_compatible_with_older_coordinator(monkeypatch):
    async def scenario():
        payloads = {
            "/health": (200, {"aggregation_mode": "none"}),
            "/clients": (200, {"clients": []}),
            "/rounds/current": (404, {}),
            "/model/current": (200, {"model_version": 0, "parameters": [0.0]}),
            "/clients/status": (404, {}),
            "/rounds/progress": (404, {}),
        }

        def fake_request(method, url, **kwargs):
            code, payload = payloads[url.removeprefix("http://coordinator:8000")]
            return SimpleNamespace(status_code=code, ok=code < 400,
                                   json=lambda: payload)

        monkeypatch.setattr(gui, "api_request", fake_request)
        app = gui.build_app("coordinator", "http://coordinator:8000")
        endpoint = next(route.endpoint for route in app.routes
                        if getattr(route, "path", None) == "/api/status")
        result = await endpoint()
        assert result["training_progress"] is None
    asyncio.run(scenario())
