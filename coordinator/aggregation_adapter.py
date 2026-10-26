#Interface for member 1 aggregation subsystem

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AggregationResult:
    accepted_clients: list[str]
    rejected_clients: list[str]
    parameters: list[float] | None
    trust_scores: dict[str, float] | None = None


class AggregationAdapter(Protocol):
    async def aggregate(
        self,
        *,
        round_id: int,
        model_version: int,
        current_parameters: list[float],
        updates: dict[str, dict],
    ) -> AggregationResult: ...


class MockAggregationAdapter:
    """Test double: manually reject named clients, average the rest.

    This is *not* FedAvg or TrustFed. Input parameters are full-model
    parameter vectors, not deltas. Replace this adapter for real training.
    """

    def __init__(self, rejected_clients=()):
        self.rejected_clients = set(rejected_clients)

    async def aggregate(
        self,
        *,
        round_id: int,
        model_version: int,
        current_parameters: list[float],
        updates: dict[str, dict],
    ) -> AggregationResult:
        accepted = sorted(set(updates) - self.rejected_clients)
        rejected = sorted(set(updates) & self.rejected_clients)

        if len(accepted) < 3:
            return AggregationResult(accepted, rejected, None)

        # Arithmetic mean solely to test the coordinator's publish workflow.
        count = len(accepted)
        parameters = [
            sum(updates[client]["parameters"][index] for client in accepted) / count
            for index in range(len(current_parameters))
        ]
        return AggregationResult(accepted, rejected, parameters)
