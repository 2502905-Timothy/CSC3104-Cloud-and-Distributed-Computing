"""Read-only committed trust-score access for remote (Kubernetes) GUI."""

import asyncio

from coordinator.aggregation_adapter import AggregationResult
from coordinator.round_manager import RoundManager


class TrustScoringAggregator:
    async def aggregate(self, **kwargs):
        clients = sorted(kwargs["updates"])
        return AggregationResult(
            accepted_clients=clients,
            rejected_clients=[],
            parameters=[0.2, 0.2, 0.2],
            trust_scores={client_id: 0.75 for client_id in clients},
        )


def test_trust_scores_are_committed_and_survive_restart(tmp_path):
    async def scenario():
        db_path = str(tmp_path / "trust-api.sqlite3")
        manager = RoundManager(db_path=db_path)
        assert await manager.trust_scores() == {
            "model_version": 0, "trust_scores": {},
        }
        started = await manager.start(60, {"a", "b", "c"})
        for client_id in ("a", "b", "c"):
            await manager.submit(
                client_id=client_id,
                round_id=started["round_id"],
                model_version=started["model_version"],
                sample_count=5,
                parameters=[0.2] * 3,
            )
        await manager.close()
        assert (await manager.finalize(TrustScoringAggregator()))["status"] == "completed"
        expected = {
            "model_version": 1,
            "trust_scores": {"a": 0.75, "b": 0.75, "c": 0.75},
        }
        assert await manager.trust_scores() == expected
        restored = RoundManager(db_path=db_path)
        assert await restored.trust_scores() == expected

    asyncio.run(scenario())
