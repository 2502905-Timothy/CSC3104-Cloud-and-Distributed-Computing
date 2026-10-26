import asyncio

import numpy as np
import pytest

from client.train import evaluate
from coordinator.aggregation import TrustFedAdapter
from shared.fed_params import N_PARAMS
from coordinator.round_manager import RoundManager
from shared.fed_params import initial_parameters
from coordinator.round_manager import AggregationFailure


TEXTS = [
    "claim your cash prize now",
    "urgent verify your bank account",
    "send your password immediately",
    "you have won a free reward",
    "meeting starts tomorrow morning",
    "please review the project report",
    "see you at lunch today",
    "the class schedule has changed",
]

LABELS = [1, 1, 1, 1, 0, 0, 0, 0]


def make_adapter(**kwargs):
    return TrustFedAdapter(TEXTS, LABELS, **kwargs)


def make_update(value=0.0, sample_count=20):
    return {
        "sample_count": sample_count,
        "parameters": [value] * N_PARAMS,
    }


def run_aggregation(adapter, updates):
    return asyncio.run(
        adapter.aggregate(
            round_id=1,
            model_version=0,
            current_parameters=[0.0] * N_PARAMS,
            updates=updates,
        )
    )


def test_three_valid_clients_are_accepted():
    adapter = make_adapter()

    updates = {
        "client_a": make_update(0.01),
        "client_b": make_update(0.02),
        "client_c": make_update(0.03),
    }

    result = run_aggregation(adapter, updates)

    assert result.accepted_clients == [
        "client_a",
        "client_b",
        "client_c",
    ]
    assert result.rejected_clients == []
    assert result.parameters is not None
    assert len(result.parameters) == N_PARAMS


def test_fewer_than_three_clients_skips_aggregation():
    adapter = make_adapter()

    updates = {
        "client_a": make_update(0.01),
        "client_b": make_update(0.02),
    }

    result = run_aggregation(adapter, updates)

    assert len(result.accepted_clients) == 2
    assert result.parameters is None
    assert adapter.trust_scores == {}


@pytest.mark.parametrize("invalid_parameters", [
    [0.0],
    [float("nan")] * N_PARAMS,
    [float("inf")] * N_PARAMS,
])
def test_invalid_parameters_are_rejected(invalid_parameters):
    adapter = make_adapter()

    updates = {
        "client_a": make_update(0.01),
        "client_b": make_update(0.02),
        "client_c": make_update(0.03),
        "bad_client": {
            "sample_count": 20,
            "parameters": invalid_parameters,
        },
    }

    result = run_aggregation(adapter, updates)

    assert "bad_client" in result.rejected_clients
    assert "bad_client" not in result.accepted_clients


def test_trust_scores_follow_proposal_formula():
    adapter = make_adapter(initial_trust=0.5)

    updates = {
        "client_a": make_update(0.01),
        "client_b": make_update(0.02),
        "client_c": make_update(0.03),
    }

    result = run_aggregation(adapter, updates)

    assert adapter.trust_scores == {}

    assert result.parameters is not None

    for client_id in result.accepted_clients:
        candidate_f1 = evaluate(
            updates[client_id]["parameters"],
            TEXTS,
            LABELS,
        )["f1"]

        expected_trust = 0.7 * 0.5 + 0.3 * candidate_f1

        assert result.trust_scores[client_id] == pytest.approx(
            expected_trust
        )


def test_trust_weighted_aggregation():
    adapter = make_adapter()

    updates = {
        "client_a": make_update(0.01, 10),
        "client_b": make_update(0.02, 20),
        "client_c": make_update(0.03, 30),
    }

    result = run_aggregation(adapter, updates)

    assert result.parameters is not None

    counts = np.array([10, 20, 30], dtype=float)
    trust = np.array([
        result.trust_scores["client_a"],
        result.trust_scores["client_b"],
        result.trust_scores["client_c"],
    ])

    weights = counts * trust
    expected = np.average(
        [0.01, 0.02, 0.03],
        weights=weights,
    )

    assert result.parameters[0] == pytest.approx(expected)
    assert np.allclose(result.parameters, expected)


def test_malicious_update_is_rejected():
    adapter = make_adapter(
        magnitude_multiplier=3.0,
        f1_drop_threshold=0.10,
    )

    # Build a model that correctly classifies the validation examples.
    from shared.fed_params import make_vectorizer

    X = make_vectorizer().transform(TEXTS)
    y = np.asarray(LABELS)

    # Find a separating direction using the labelled examples.
    positive = np.asarray(X[y == 1].mean(axis=0)).ravel()
    negative = np.asarray(X[y == 0].mean(axis=0)).ravel()

    direction = positive - negative
    direction /= max(np.linalg.norm(direction), 1e-12)

    good_parameters = np.concatenate([
        direction * 10.0,
        np.array([0.0]),
    ]).tolist()

    # The opposite direction is intentionally harmful.
    malicious_parameters = np.concatenate([
        -direction * 1000.0,
        np.array([0.0]),
    ]).tolist()

    # Compare candidate-model F1 values explicitly.
    good_f1 = evaluate(good_parameters, TEXTS, LABELS)["f1"]
    bad_f1 = evaluate(malicious_parameters, TEXTS, LABELS)["f1"]

    assert good_f1 > bad_f1

    # Set the global model to the good parameters.
    async def execute():
        return await adapter.aggregate(
            round_id=1,
            model_version=0,
            current_parameters=good_parameters,
            updates={
                "client_a": {
                    "sample_count": 20,
                    "parameters": good_parameters,
                },
                "client_b": {
                    "sample_count": 20,
                    "parameters": good_parameters,
                },
                "client_c": {
                    "sample_count": 20,
                    "parameters": good_parameters,
                },
                "malicious_client": {
                    "sample_count": 20,
                    "parameters": malicious_parameters,
                },
            },
        )

    result = asyncio.run(execute())

    assert "malicious_client" in result.rejected_clients
    assert "malicious_client" not in result.accepted_clients
    assert len(result.accepted_clients) == 3
    assert result.parameters is not None
    assert np.allclose(result.parameters, good_parameters)

def test_trust_scores_survive_coordinator_restart(tmp_path):
    db_path = str(tmp_path / "trustfed_test.sqlite3")

    async def execute():
        manager = RoundManager(
            initial_parameters=initial_parameters(),
            db_path=db_path,
        )

        adapter = make_adapter()

        for client_id in ("client_a", "client_b", "client_c"):
            await manager.register(client_id)

        round_info = await manager.start(deadline_seconds=60)

        for client_id, value in (
            ("client_a", 0.01),
            ("client_b", 0.02),
            ("client_c", 0.03),
        ):
            await manager.submit(
                client_id=client_id,
                round_id=round_info["round_id"],
                model_version=round_info["model_version"],
                sample_count=20,
                parameters=[value] * N_PARAMS,
            )

        await manager.close()
        result = await manager.finalize(adapter)

        assert result["status"] == "completed"
        assert result["current_model_version"] == 1

        original_trust = dict(manager._state["trust_scores"])
        assert len(original_trust) == 3

        # Simulate restarting the coordinator.
        restarted = RoundManager(
            initial_parameters=initial_parameters(),
            db_path=db_path,
        )

        assert restarted._state["trust_scores"] == original_trust

    asyncio.run(execute())

def test_failed_publication_preserves_trust_and_allows_retry(tmp_path):
    db_path = str(tmp_path / "retry_test.sqlite3")

    async def execute():
        manager = RoundManager(
            initial_parameters=initial_parameters(),
            db_path=db_path,
        )
        adapter = make_adapter()

        for client_id in ("client_a", "client_b", "client_c"):
            await manager.register(client_id)

        round_info = await manager.start(deadline_seconds=60)

        for client_id, value in (
            ("client_a", 0.01),
            ("client_b", 0.02),
            ("client_c", 0.03),
        ):
            await manager.submit(
                client_id=client_id,
                round_id=round_info["round_id"],
                model_version=round_info["model_version"],
                sample_count=20,
                parameters=[value] * N_PARAMS,
            )

        await manager.close()

        original_trust = dict(manager._state["trust_scores"])
        original_version = (await manager.model())["model_version"]

        # Simulate a database failure during the final publication.
        original_commit = manager._commit
        failed_once = False

        def failing_commit(proposed):
            nonlocal failed_once

            if (
                not failed_once
                and proposed["current"]["status"] == "completed"
            ):
                failed_once = True
                raise OSError("Simulated publication failure")

            return original_commit(proposed)

        manager._commit = failing_commit

        with pytest.raises(OSError, match="Simulated publication failure"):
            await manager.finalize(adapter)

        assert manager._state["trust_scores"] == original_trust
        assert (await manager.model())["model_version"] == original_version

        # Restore normal database operations.
        manager._commit = original_commit

        # Simulate a coordinator restart after interrupted publication.
        restarted = RoundManager(
            initial_parameters=initial_parameters(),
            db_path=db_path,
        )

        assert restarted._state["trust_scores"] == original_trust
        assert (await restarted.model())["model_version"] == original_version

        # Retry the same round.
        result = await restarted.finalize(make_adapter())

        assert result["status"] == "completed"
        assert result["current_model_version"] == original_version + 1
        assert len(restarted._state["trust_scores"]) == 3

    asyncio.run(execute())