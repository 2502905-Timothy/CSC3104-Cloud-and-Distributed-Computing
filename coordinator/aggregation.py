"""Trust-aware aggregation for federated scam-message detection."""

import math

import numpy as np

from client.train import evaluate
from coordinator.aggregation_adapter import AggregationResult


class TrustFedAdapter:
    def __init__(
        self,
        validation_texts,
        validation_labels,
        initial_trust=0.5,
        trust_decay=0.7,
        max_weight_ratio=2.0,
        magnitude_multiplier=3.0,
        f1_drop_threshold=0.10,
    ):
        if not validation_texts or len(validation_texts) != len(validation_labels):
            raise ValueError("A nonempty, aligned validation dataset is required")
        if set(validation_labels) - {0, 1}:
            raise ValueError("Validation labels must be 0 or 1")
        if not 0 <= initial_trust <= 1:
            raise ValueError("Initial trust must be between 0 and 1")
        if not 0 <= trust_decay <= 1:
            raise ValueError("Trust decay must be between 0 and 1")
        if max_weight_ratio <= 0 or magnitude_multiplier <= 0:
            raise ValueError("Weight and magnitude ratios must be positive")
        if not 0 <= f1_drop_threshold <= 1:
            raise ValueError("F1 drop threshold must be between 0 and 1")

        self.validation_texts = list(validation_texts)
        self.validation_labels = list(validation_labels)
        self.initial_trust = initial_trust
        self.trust_decay = trust_decay
        self.max_weight_ratio = max_weight_ratio
        self.magnitude_multiplier = magnitude_multiplier
        self.f1_drop_threshold = f1_drop_threshold

        self.trust_scores = {}

    async def aggregate(
        self,
        *,
        round_id,
        model_version,
        current_parameters,
        updates,
    ) -> AggregationResult:
        base = np.asarray(current_parameters, dtype=np.float64)

        if base.ndim != 1 or not np.all(np.isfinite(base)):
            raise ValueError("Invalid global model parameters")

        current_f1 = float(
            evaluate(
                current_parameters,
                self.validation_texts,
                self.validation_labels,
            )["f1"]
        )

        valid = {}
        rejected = []
        magnitudes = {}

        # First pass: reject malformed updates.
        for client_id in sorted(updates):
            update = updates[client_id]

            try:
                parameters = np.asarray(
                    update["parameters"],
                    dtype=np.float64,
                )
                sample_count = update["sample_count"]

                if (
                    parameters.shape != base.shape
                    or not np.all(np.isfinite(parameters))
                    or not isinstance(sample_count, int)
                    or sample_count < 1
                ):
                    raise ValueError("Invalid client update")

                magnitude = float(
                    np.linalg.norm(parameters - base)
                )

                if not math.isfinite(magnitude):
                    raise ValueError("Invalid update magnitude")

                valid[client_id] = {
                    "parameters": parameters,
                    "sample_count": sample_count,
                }
                magnitudes[client_id] = magnitude

            except (KeyError, TypeError, ValueError, OverflowError):
                rejected.append(client_id)

        if not valid:
            return AggregationResult([], sorted(rejected), None)

        median_magnitude = float(
            np.median(list(magnitudes.values()))
        )

        accepted = []
        candidate_f1 = {}

        # Second pass: evaluate candidate models and detect anomalies.
        for client_id in sorted(valid):
            parameters = valid[client_id]["parameters"]

            f1 = float(
                evaluate(
                    parameters.tolist(),
                    self.validation_texts,
                    self.validation_labels,
                )["f1"]
            )

            anomalous_magnitude = (
                magnitudes[client_id]
                > self.magnitude_multiplier * max(
                    median_magnitude, 1e-12
                )
            )

            significant_f1_drop = (
                current_f1 - f1 > self.f1_drop_threshold
            )

            if anomalous_magnitude and significant_f1_drop:
                rejected.append(client_id)
            else:
                accepted.append(client_id)
                candidate_f1[client_id] = f1

        if len(accepted) < 3:
            return AggregationResult(
                sorted(accepted),
                sorted(rejected),
                None,
            )

        # Calculate updated trust scores.
        proposed_trust = {}

        for client_id in accepted:
            previous = self.trust_scores.get(
                client_id,
                self.initial_trust,
            )

            proposed_trust[client_id] = (
                self.trust_decay * previous
                + (1 - self.trust_decay) * candidate_f1[client_id]
            )

        counts = np.asarray(
            [valid[c]["sample_count"] for c in accepted],
            dtype=np.float64,
        )

        cap = self.max_weight_ratio * float(np.median(counts))
        capped_counts = np.minimum(counts, cap)

        trust = np.asarray(
            [proposed_trust[c] for c in accepted],
            dtype=np.float64,
        )

        weights = capped_counts * trust

        if not np.all(np.isfinite(weights)) or weights.sum() <= 0:
            # Avoid division by zero if all clients have zero trust.
            weights = capped_counts

        weights = weights / weights.sum()

        stacked = np.stack(
            [valid[c]["parameters"] for c in accepted]
        )

        aggregated = np.sum(
            stacked * weights[:, None],
            axis=0,
        )

        if not np.all(np.isfinite(aggregated)):
            raise ValueError("Aggregation produced invalid parameters")

        # Return proposed trust scores without committing them.
        # The coordinator will persist them atomically with the global model.
        return AggregationResult(
            sorted(accepted),
            sorted(rejected),
            aggregated.tolist(),
            trust_scores={
                **self.trust_scores,
                **proposed_trust,
            },
        )
