# This class is the object it calls for the Fedavg baseline.

from coordinator.aggregation_adapter import AggregationResult
from shared.fedavg import fedavg

class FedAvgAdapter:
    def __init__(self, max_weight_ratio: float | None = None):
        self.max_weight_ratio = max_weight_ratio
    
    
    # Called by the coordinator once per round
    # Returns an AggregationResult saying which clients are accepted, which are rejected,
    # and the new global parameters.
    async def aggregate(self, *, round_id, model_version, current_parameters, updates) -> AggregationResult:
        clients = sorted(updates)
        
        # Coordinator's rule: Fewer than 3 accepted updates = no new model.
        if len(clients) < 3:
            return AggregationResult(clients, [], None)
        
        #FedAvg trusts everyone, all clients accepted, none rejected.
        return AggregationResult (clients, [], fedavg(updates, self.max_weight_ratio))