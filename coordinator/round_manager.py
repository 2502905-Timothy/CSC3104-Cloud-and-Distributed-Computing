#State lost on restart
#Application must run with 1 Uvicorn work until shared storage is added

import asyncio
import math
from datetime import datetime, timedelta, timezone
from time import monotonic

from coordinator.aggregation_adapter import AggregationResult


class AggregationFailure(Exception):
    """Aggregation failed; the global model was not modified."""


class RoundManager:
    def __init__(self, initial_parameters: list[float] | None = None):
        # Temporary three-parameter model for isolated coordinator testing.
        # Role 2 must supply the actual model and its agreed representation.
        parameters = [0.0, 0.0, 0.0] if initial_parameters is None else list(initial_parameters)
        if not parameters or not all(math.isfinite(value) for value in parameters):
            raise ValueError("Initial model parameters must be finite and nonempty")

        self._lock = asyncio.Lock()
        self._current = None
        self._round_number = 1
        self._model_version = 0
        self._model_parameters = parameters
        self._deadline_clock = None
        self._participants: set[str] = set()
        self._updates: dict[str, dict] = {}

    def _update_deadline_locked(self):
        # Deadline enforcement is request-driven for now, not a background job.
        if (
            self._current is not None
            and self._current["status"] == "collecting"
            and monotonic() >= self._deadline_clock
        ):
            self._current["status"] = "deadline_reached"

    def _summary_locked(self):
        return {
            **self._current,
            "participants": sorted(self._participants),
            "submissions_received": len(self._updates),
            "submitted_clients": sorted(self._updates),
            "current_model_version": self._model_version,
        }

    async def model(self):
        async with self._lock:
            return {
                "model_version": self._model_version,
                "parameters": list(self._model_parameters),
            }

    async def start(self, deadline_seconds: int, participants: set[str]):
        if not 1 <= deadline_seconds <= 3600:
            raise ValueError("Deadline must be between 1 and 3600 seconds")
        async with self._lock:
            self._update_deadline_locked()
            if (
                self._current is not None
                and self._current["status"]
                not in {"completed", "skipped_insufficient_updates"}
            ):
                raise ValueError("A round already exists; it must be finalised first")

            started = datetime.now(timezone.utc)
            self._deadline_clock = monotonic() + deadline_seconds
            self._participants = set(participants)
            self._updates = {}
            self._current = {
                "round_id": self._round_number,
                "model_version": self._model_version,
                "status": "collecting",
                "started_at": started.isoformat(),
                "deadline_at": (
                    started + timedelta(seconds=deadline_seconds)
                ).isoformat(),
            }
            self._round_number += 1
            return self._summary_locked()

    async def current(self):
        async with self._lock:
            self._update_deadline_locked()
            return self._summary_locked() if self._current is not None else None

    async def submit(
        self,
        *,
        client_id: str,
        round_id: int,
        model_version: int,
        sample_count: int,
        parameters: list[float],
    ):
        async with self._lock:
            self._update_deadline_locked()
            if self._current is None:
                raise ValueError("No training round exists")
            if round_id != self._current["round_id"]:
                raise ValueError("Update belongs to a different round")
            if model_version != self._current["model_version"]:
                raise ValueError("Update uses an incorrect model version")
            if self._current["status"] != "collecting":
                raise ValueError("Round is no longer collecting updates")
            if client_id not in self._participants:
                raise ValueError("Client is not participating in this round")
            if client_id in self._updates:
                raise ValueError("Client already submitted an update for this round")
            if sample_count < 1:
                raise ValueError("Sample count must be positive")
            if len(parameters) != len(self._model_parameters):
                raise ValueError("Update parameter count does not match global model")
            if not all(math.isfinite(value) for value in parameters):
                raise ValueError("Update contains non-finite parameter values")

            # Received does not imply validated or accepted by Role 1.
            self._updates[client_id] = {
                "sample_count": sample_count,
                "parameters": list(parameters),
            }
            return {
                "client_id": client_id,
                "round_id": round_id,
                "status": "received_unvalidated",
                "submissions_received": len(self._updates),
            }

    async def close(self):
        async with self._lock:
            self._update_deadline_locked()
            if self._current is None:
                raise ValueError("No training round exists")
            if self._current["status"] not in {"collecting", "deadline_reached"}:
                raise ValueError("Round has already been closed")
            if (
                self._current["status"] == "collecting"
                and len(self._updates) < len(self._participants)
            ):
                raise ValueError("Cannot close before the deadline while clients are pending")

            self._current["closed_at"] = datetime.now(timezone.utc).isoformat()
            if len(self._updates) < 3:
                self._current["status"] = "skipped_insufficient_updates"
                self._current["accepted_clients"] = []
                self._current["rejected_clients"] = []
            else:
                self._current["status"] = "awaiting_validation"
            return self._summary_locked()

    @staticmethod
    def _verify_result(result, updates, expected_dimensions):
        if not isinstance(result, AggregationResult):
            raise ValueError("Aggregation adapter returned the wrong result type")
        accepted = result.accepted_clients
        rejected = result.rejected_clients
        if (
            len(accepted) != len(set(accepted))
            or len(rejected) != len(set(rejected))
            or set(accepted) & set(rejected)
            or set(accepted) | set(rejected) != set(updates)
        ):
            raise ValueError("Aggregation adapter returned inconsistent client IDs")
        if len(accepted) < 3:
            if result.parameters is not None:
                raise ValueError("Aggregation returned parameters with fewer than 3 accepted updates")
        elif (
            result.parameters is None
            or len(result.parameters) != expected_dimensions
            or not all(math.isfinite(value) for value in result.parameters)
        ):
            raise ValueError("Aggregation returned invalid model parameters")

    async def finalize(self, aggregator):
        # Phase 1: reserve this round under lock. Only one caller may aggregate.
        async with self._lock:
            if self._current is None or self._current["status"] not in {
                "awaiting_validation", "aggregation_failed"
            }:
                raise ValueError("Round is not ready for aggregation")
            self._current["status"] = "aggregating"
            round_id = self._current["round_id"]
            model_version = self._current["model_version"]
            base_model = list(self._model_parameters)
            updates = {
                client_id: {
                    "sample_count": data["sample_count"],
                    "parameters": list(data["parameters"]),
                }
                for client_id, data in self._updates.items()
            }

        try:
            result = await aggregator.aggregate(
                round_id=round_id,
                model_version=model_version,
                current_parameters=base_model,
                updates=updates,
            )
            self._verify_result(result, updates, len(base_model))
        except BaseException as exc:
            # A failed/cancelled adapter must not publish a partially updated model.
            async with self._lock:
                if self._current["round_id"] == round_id:
                    self._current["status"] = "aggregation_failed"
            if isinstance(exc, asyncio.CancelledError):
                raise
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise AggregationFailure("Aggregation failed; global model unchanged") from exc

        # Phase 2: publish atomically, after validation succeeds.
        async with self._lock:
            if (
                self._current["round_id"] != round_id
                or self._current["status"] != "aggregating"
                or self._model_version != model_version
            ):
                raise AggregationFailure("Round changed during aggregation")

            self._current["accepted_clients"] = sorted(result.accepted_clients)
            self._current["rejected_clients"] = sorted(result.rejected_clients)
            self._current["finalized_at"] = datetime.now(timezone.utc).isoformat()
            if len(result.accepted_clients) < 3:
                self._current["status"] = "skipped_insufficient_updates"
            else:
                self._model_parameters = list(result.parameters)
                self._model_version += 1
                self._current["status"] = "completed"
            return self._summary_locked()
