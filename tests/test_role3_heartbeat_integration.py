"""Stage 2 readiness: client reporting and coordinator GUI visibility."""

import asyncio
from threading import Event
from types import SimpleNamespace

import client.client as cli
import visualization.app as gui


def test_kubernetes_cli_heartbeat_contains_no_csv_rows(monkeypatch):
    sent = []
    stop = Event()

    def fake_post(url, json, timeout):
        sent.append((url, json, timeout))
        stop.set()
        return SimpleNamespace(status_code=200)

    monkeypatch.setattr(cli.requests, "post", fake_post)
    cli.heartbeat_loop("client-1", 781, "http://coordinator:8000", stop)

    assert sent == [(
        "http://coordinator:8000/clients/heartbeat",
        {"client_id": "client-1", "dataset_ready": True, "sample_count": 781},
        8,
    )]


def test_uploaded_csv_gui_client_heartbeat(monkeypatch):
    async def scenario():
        client = gui.LocalClient("http://coordinator:8000")
        client.client_id = "client-2"
        client.texts = ["first", "second"]
        client.labels = [0, 1]
        client.running = True
        sent = []

        def fake_request(method, url, **kwargs):
            sent.append((method, url, kwargs["json"]))
            client.running = False
            return SimpleNamespace(status_code=200)

        monkeypatch.setattr(gui, "api_request", fake_request)
        await client.send_heartbeats()
        assert sent == [(
            "POST", "http://coordinator:8000/clients/heartbeat",
            {"client_id": "client-2", "dataset_ready": True, "sample_count": 2},
        )]

    asyncio.run(scenario())


def test_coordinator_gui_exposes_live_status(monkeypatch):
    async def scenario():
        called = []
        payloads = {
            "/health": (200, {"aggregation_mode": "none"}),
            "/clients": (200, {"clients": ["client-1"]}),
            "/rounds/current": (404, {"detail": "No training round"}),
            "/model/current": (200, {"model_version": 0, "parameters": [0.0]}),
            "/rounds/progress": (200, {"target_successful_rounds": 5,
                                       "successful_rounds": 0, "skipped_rounds": 0,
                                       "ready_for_evaluation": False}),
            "/clients/status": (200, {"clients": [{"client_id": "client-1", "online": True,
                          "dataset_ready": True, "sample_count": 781}],
                          "online_count": 1, "ready_count": 1}),
        }

        def fake_request(method, url, **kwargs):
            path = url.removeprefix("http://coordinator:8000")
            called.append((method, path))
            code, body = payloads[path]
            return SimpleNamespace(status_code=code, ok=code < 400, json=lambda: body)

        monkeypatch.setattr(gui, "api_request", fake_request)
        app = gui.build_app("coordinator", "http://coordinator:8000")
        endpoint = next(route.endpoint for route in app.routes if getattr(route, "path", None) == "/api/status")
        result = await endpoint()
        assert result["client_statuses"]["ready_count"] == 1
        assert result["client_statuses"]["clients"][0]["sample_count"] == 781
        assert ("GET", "/clients/status") in called

    asyncio.run(scenario())
