"""Local real-training integration test for TrustFed's 3-client, 5-round plan.

This exercises actual CSV data, client training, TrustFed aggregation,
SQLite persistence and final read-only scoring. It does not test Kubernetes,
HTTP networking or the browser GUIs.
"""

import asyncio
from pathlib import Path

import pytest

from client.client import load_csv
from client.train import local_train
from coordinator.aggregation import TrustFedAdapter
from coordinator.round_manager import RoundManager
from shared.fed_params import initial_parameters
from visualization.final_evaluation import evaluate_final_model


ROOT = Path(__file__).resolve().parents[1]


def test_three_real_clients_five_successful_rounds_then_evaluate(tmp_path):
    async def scenario():
        db_path = str(tmp_path / "trustfed-e2e.sqlite3")
        manager = RoundManager(
            initial_parameters=initial_parameters(), db_path=db_path,
        )
        validation_texts, validation_labels = load_csv(
            str(ROOT / "data" / "coordinator_val_set.csv")
        )
        aggregator = TrustFedAdapter(validation_texts, validation_labels)

        clients = {
            f"client-{index}": load_csv(
                str(ROOT / "data" / f"client_{index}_train.csv")
            )
            for index in (1, 2, 3)
        }

        for client_id, (texts, _labels) in clients.items():
            await manager.register(client_id)
            await manager.heartbeat(client_id, True, len(texts))

        status = await manager.client_statuses()
        assert status["online_count"] == 3
        assert status["ready_count"] == 3

        for expected_version in range(1, 6):
            round_info = await manager.start(deadline_seconds=30)
            global_model = await manager.model()
            for client_id, (texts, labels) in clients.items():
                updated = local_train(
                    global_model["parameters"], texts, labels,
                    epochs=3, seed=round_info["round_id"],
                )
                await manager.submit(
                    client_id=client_id,
                    round_id=round_info["round_id"],
                    model_version=round_info["model_version"],
                    sample_count=len(texts),
                    parameters=updated,
                )

            await manager.close()
            result = await manager.finalize(aggregator)
            assert result["status"] == "completed"
            assert sorted(result["accepted_clients"]) == sorted(clients)
            assert result["rejected_clients"] == []
            assert (await manager.model())["model_version"] == expected_version

        progress = await manager.training_progress()
        assert progress["successful_rounds"] == 5
        assert progress["attempted_rounds"] == 5
        assert progress["skipped_rounds"] == 0
        assert progress["ready_for_evaluation"] is True

        final_model = await manager.model()
        original_parameters = final_model["parameters"].copy()
        test_texts, test_labels = load_csv(str(ROOT / "data" / "final_test_set.csv"))
        evaluation = evaluate_final_model(
            final_model["parameters"], test_texts, test_labels,
        )
        assert evaluation["sample_count"] == len(test_labels)
        for metric in ("accuracy", "precision", "recall", "f1"):
            assert 0 <= evaluation[metric] <= 1
        assert final_model["parameters"] == original_parameters

        restored = RoundManager(
            initial_parameters=initial_parameters(), db_path=db_path,
        )
        assert (await restored.training_progress())["successful_rounds"] == 5
        with pytest.raises(ValueError, match="Five successful rounds"):
            await restored.start(30)

    asyncio.run(scenario())
