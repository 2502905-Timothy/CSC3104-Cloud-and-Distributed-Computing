# Run: python -m pytest -q tests/test_role2_federated.py

# This file has three types of test:
#     1. FedAvg - is the averaging math correct?
#     2. Adapter - Does FedAvg work inside roundmanager
#     3. Training - does a client produce a sensible update, and does the whole federated loop actually learn?

import asyncio
import random
import pytest

from client.train import evaluate, local_train
from coordinator.aggregation_adapter import AggregationResult
from coordinator.fedavg_adapter import FedAvgAdapter
from coordinator.round_manager import RoundManager
from shared.fed_params import N_PARAMS, initial_parameters
from shared.fedavg import fedavg


def run(coroutine):
    # The coordinator code is async; this runs an async test scenario to completion.
    return asyncio.run(coroutine)
 
 
def update(count, params):
    # Helper: build one client's update in the coordinator's format.
    return {"sample_count": count, "parameters": params}
 
 
# 1. FedAvg 
 
def test_fedavg_weights_by_sample_count():
    # Client a has 3x the data of client b, so the answer should sit 3/4 of the way to a.
    # Parameter 1: (300*1 + 100*5)/400 = 2.0.  Parameter 2: (300*0 + 100*4)/400 = 1.0.
    result = fedavg({"a": update(300, [1.0, 0.0]), "b": update(100, [5.0, 4.0])})
    assert result == pytest.approx([2.0, 1.0])
 
 
def test_fedavg_cap_limits_dominant_client():
    updates = {
        "a": update(100, [0.0]),
        "b": update(100, [0.0]),
        "huge": update(1_000_000, [10.0]),   # one client with enormously more data
    }
    uncapped = fedavg(updates)[0]
    capped = fedavg(updates, max_weight_ratio=1.0)[0]   # huge counts as 100, like the others
    assert uncapped > 9.9                    # without a cap, "huge" completely dominates
    assert capped == pytest.approx(10.0 / 3) # with the cap, all three count equally
 
 
def test_fedavg_rejects_empty_input():
    with pytest.raises(ValueError):
        fedavg({})
 
 
# 2. Adapter inside the real RoundManager 
 
def test_adapter_publishes_weighted_average_through_round_manager():
    async def scenario():
        manager = RoundManager()                       # 3-parameter model is enough here
        info = await manager.start(30, {"a", "b", "c"})
 
        # Three clients submit; c has twice the data of a or b.
        for cid, count, value in (("a", 10, 1.0), ("b", 10, 2.0), ("c", 20, 4.0)):
            await manager.submit(
                client_id=cid, round_id=info["round_id"],
                model_version=info["model_version"],
                sample_count=count, parameters=[value] * 3,
            )
        await manager.close()                          # closes the round (all 3 submitted)
        result = await manager.finalize(FedAvgAdapter())   # runs aggregation and publishes
 
        assert result["status"] == "completed"
        assert result["accepted_clients"] == ["a", "b", "c"]
        assert result["rejected_clients"] == []        # FedAvg rejects nobody
        model = await manager.model()
        assert model["model_version"] == 1             # version went up by one
        assert model["parameters"] == pytest.approx([2.75] * 3)   # (10*1 + 10*2 + 20*4)/40
 
    run(scenario())
 
 
def test_adapter_returns_no_parameters_below_three_updates():
    async def scenario():
        result = await FedAvgAdapter().aggregate(
            round_id=1, model_version=0, current_parameters=[0.0],
            updates={"a": update(1, [1.0]), "b": update(1, [2.0])},
        )
        assert isinstance(result, AggregationResult)
        assert result.parameters is None               # None = "do not publish a new model"
        assert result.accepted_clients == ["a", "b"]
 
    run(scenario())
 
 
# 3. Local training 
 
# Tiny vocabularies used to generate fake "scam" and "legitimate" messages for tests.
SCAM = "urgent verify account bank click link prize winner claim free password otp".split()
LEGIT = "hi lunch tomorrow meeting thanks dinner family movie weekend call project".split()
 
 
# Generate n fake messages; each is a scam with probability p_scam.
# Each message is mostly words from its own class plus one "noise" word from
# the other class, so the task is easy but not perfectly trivial.
def make_messages(n, p_scam, rng):
    
    texts, labels = [], []
    for _ in range(n):
        y = int(rng.random() < p_scam)
        pool, other = (SCAM, LEGIT) if y else (LEGIT, SCAM)
        words = [rng.choice(pool) for _ in range(6)] + [rng.choice(other)]
        rng.shuffle(words)
        texts.append(" ".join(words))
        labels.append(y)
    return texts, labels
 
 
def test_local_train_returns_finite_update_of_correct_size():
    texts, labels = make_messages(60, 0.5, random.Random(0))
    new = local_train(initial_parameters(), texts, labels)
    assert len(new) == N_PARAMS                        # same size the coordinator expects
    assert all(abs(x) < 1e6 for x in new)              # no exploding / NaN-like values
    assert new != initial_parameters()                 # training actually changed the model
 
 
def test_local_train_handles_client_with_only_one_class():
    # Non-IID case: this client has ONLY scam messages. Training must not crash.
    texts, labels = make_messages(30, 1.0, random.Random(1))
    assert set(labels) == {1}
    new = local_train(initial_parameters(), texts, labels)
    assert len(new) == N_PARAMS
    assert new[-1] > 0                                  # intercept moves towards "scam"
 
 
def test_local_train_does_not_mutate_its_input():
    # The global model list must be untouched, because other clients share the same one.
    start = initial_parameters()
    texts, labels = make_messages(30, 0.5, random.Random(2))
    local_train(start, texts, labels)
    assert start == initial_parameters()
 
 
def test_federated_rounds_learn_without_any_server():
    # A full federated simulation in one process: 4 clients with different sizes and
    # class balance (non-IID), 4 rounds of train -> FedAvg, then test the global model.
    rng = random.Random(3)
    clients = [make_messages(n, p, rng) for n, p in ((120, 0.5), (60, 0.8), (90, 0.2), (30, 1.0))]
    test_texts, test_labels = make_messages(300, 0.5, rng)   # held-out data no client trained on
 
    params = initial_parameters()
    for round_id in range(1, 5):
        # Every client trains from the same current global model...
        updates = {
            f"c{i}": {
                "sample_count": len(texts),
                "parameters": local_train(params, texts, labels, seed=round_id),
            }
            for i, (texts, labels) in enumerate(clients)
        }
        # ...and the server averages the results into the next global model.
        params = fedavg(updates)

    assert evaluate(params, test_texts, test_labels)["f1"] > 0.9