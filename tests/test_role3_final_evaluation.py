"""Stage 4: final evaluation is read-only and gated on five successes."""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from coordinator.aggregation_adapter import MockAggregationAdapter
from coordinator.round_manager import RoundManager
from shared.fed_params import initial_parameters, make_vectorizer, N_PARAMS
from visualization.final_evaluation import evaluate_final_model
import visualization.app as gui


CSV = "message,label\nfree reward claim,1\nproject meeting tomorrow,0\n"


def _endpoint(app, path):
    return next(route.endpoint for route in app.routes if getattr(route, "path", None) == path)


def test_zero_model_metrics_and_no_mutation():
    params = initial_parameters()
    before = list(params)
    result = evaluate_final_model(params, ["win prize", "project meeting"], [1, 0])
    assert result == {
        "sample_count": 2,
        "accuracy": 0.5,
        "precision": 0.0,
        "recall": 0.0,
        "f1": 0.0,
    }
    assert params == before


def test_actual_hashing_model_used_for_perfect_separation():
    # Build a separating vector in the same hashing feature space as training.
    import numpy as np

    texts = ["claim free reward", "project meeting tomorrow"]
    features = make_vectorizer().transform(texts).toarray()
    direction = features[0] - features[1]
    assert direction @ features[0] > 0
    assert direction @ features[1] < 0
    params = [*direction.tolist(), 0.0]
    assert len(params) == N_PARAMS
    result = evaluate_final_model(params, texts, [1, 0])
    for metric in ("accuracy", "precision", "recall", "f1"):
        assert result[metric] == pytest.approx(1.0)


def test_invalid_model_and_dataset():
    with pytest.raises(ValueError, match="Expected"):
        evaluate_final_model([0.0], ["text"], [0])
    with pytest.raises(ValueError, match="non-finite"):
        evaluate_final_model([float("nan")] * N_PARAMS, ["text"], [1])
    with pytest.raises(ValueError, match="labels"):
        evaluate_final_model(initial_parameters(), ["text"], [2])
    with pytest.raises(ValueError, match="labelled"):
        evaluate_final_model(initial_parameters(), [], [])


def test_gui_evaluation_blocked_until_five_successes(monkeypatch):
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url))
        assert url.endswith("/rounds/progress")
        return SimpleNamespace(ok=True, status_code=200, json=lambda: {
            "successful_rounds": 4, "ready_for_evaluation": False,
        })

    monkeypatch.setattr(gui, "api_request", fake_request)
    endpoint = _endpoint(gui.build_app("coordinator", "http://coord"), "/api/evaluate")

    async def scenario():
        with pytest.raises(HTTPException) as exc:
            await endpoint(gui.FinalEvaluationRequest(csv_text=CSV))
        assert exc.value.status_code == 409

    asyncio.run(scenario())
    assert calls == [("GET", "http://coord/rounds/progress")]


def test_gui_evaluates_final_model_without_posting_to_coordinator(monkeypatch):
    calls = []
    params = initial_parameters()
    original = list(params)

    def fake_request(method, url, **kwargs):
        calls.append((method, url))
        if url.endswith("/rounds/progress"):
            data = {"successful_rounds": 5, "ready_for_evaluation": True}
        elif url.endswith("/model/current"):
            data = {"model_version": 5, "parameters": params}
        else:
            raise AssertionError("Unexpected coordinator request")
        return SimpleNamespace(ok=True, status_code=200, json=lambda: data)

    monkeypatch.setattr(gui, "api_request", fake_request)
    endpoint = _endpoint(gui.build_app("coordinator", "http://coord"), "/api/evaluate")
    result = asyncio.run(endpoint(gui.FinalEvaluationRequest(csv_text=CSV)))
    assert result == {
        "model_version": 5,
        "sample_count": 2,
        "accuracy": 0.5,
        "precision": 0.0,
        "recall": 0.0,
        "f1": 0.0,
    }
    assert params == original
    assert calls == [
        ("GET", "http://coord/rounds/progress"),
        ("GET", "http://coord/model/current"),
    ]


def test_gui_rejects_invalid_csv_without_fetching_model(monkeypatch):
    monkeypatch.setattr(gui, "api_request", lambda *a, **kw: pytest.fail("Must not call coordinator"))
    endpoint = _endpoint(gui.build_app("coordinator", "http://coord"), "/api/evaluate")

    async def scenario():
        with pytest.raises(HTTPException) as exc:
            await endpoint(gui.FinalEvaluationRequest(csv_text="wrong,columns\na,b\n"))
        assert exc.value.status_code == 400

    asyncio.run(scenario())


def test_gui_rejects_changed_model_version(monkeypatch):
    def fake_request(method, url, **kwargs):
        if url.endswith("/rounds/progress"):
            payload = {"successful_rounds": 5, "ready_for_evaluation": True}
        else:
            payload = {"model_version": 6, "parameters": initial_parameters()}
        return SimpleNamespace(ok=True, status_code=200, json=lambda: payload)

    monkeypatch.setattr(gui, "api_request", fake_request)
    endpoint = _endpoint(gui.build_app("coordinator", "http://coord"), "/api/evaluate")

    async def scenario():
        with pytest.raises(HTTPException) as exc:
            await endpoint(gui.FinalEvaluationRequest(csv_text=CSV))
        assert exc.value.status_code == 409

    asyncio.run(scenario())


def test_round_manager_blocks_round_six_after_five_successes(tmp_path):
    async def scenario():
        db = str(tmp_path / "final.sqlite3")
        manager = RoundManager(db_path=db)
        for attempt in range(5):
            started = await manager.start(30, {"a", "b", "c"})
            for cid in ("a", "b", "c"):
                await manager.submit(
                    client_id=cid,
                    round_id=started["round_id"],
                    model_version=started["model_version"],
                    sample_count=1,
                    parameters=[float(attempt + 1)] * 3,
                )
            await manager.close()
            await manager.finalize(MockAggregationAdapter())
        assert (await manager.training_progress())["ready_for_evaluation"]
        with pytest.raises(ValueError, match="Five successful rounds"):
            await manager.start(30, {"a", "b", "c"})
        restored = RoundManager(db_path=db)
        with pytest.raises(ValueError, match="Five successful rounds"):
            await restored.start(30, {"a", "b", "c"})
    asyncio.run(scenario())
