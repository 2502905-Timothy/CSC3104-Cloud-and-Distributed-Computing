
"""TrustFed round manager with optional atomic local SQLite persistence.

Run only one coordinator process against a SQLite database file.
The aggregation adapter must be deterministic/idempotent for safe retries.
"""

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import math
from time import monotonic

from coordinator.aggregation_adapter import AggregationResult
from coordinator.state_store import SQLiteStateStore


class AggregationFailure(Exception):
    """Aggregation did not publish a new model."""


class RoundManager:
    def __init__(
        self,
        initial_parameters: list[float] | None = None,
        db_path: str | None = None,
    ):
        parameters = (
            [0.0, 0.0, 0.0]
            if initial_parameters is None
            else list(initial_parameters)
        )

        if not parameters or not all(math.isfinite(x) for x in parameters):
            raise ValueError(
                "Initial parameters must be finite and nonempty"
            )

        self._lock = asyncio.Lock()

        # Existing unit tests can still run without persistence.
        self._store = (
            SQLiteStateStore(db_path)
            if db_path is not None
            else None
        )

        saved = self._store.load() if self._store else None
        self._deadline_clock = None

        if saved is None:
            self._state = {
                "registered_clients": [],
                "next_round_id": 1,
                "model_version": 0,
                "model_parameters": parameters,
                "current": None,
                "participants": [],
                "updates": {},
            }

            if self._store:
                self._store.save(self._state)

        else:
            # Restore the previous model and round information.
            self._state = saved

            if self._state["current"] is not None:
                if self._state["current"]["status"] == "aggregating":
                    recovered = deepcopy(self._state)

                    recovered["current"]["status"] = (
                        "aggregation_failed"
                    )

                    recovered["current"]["recovery_reason"] = (
                        "Coordinator restarted during aggregation; "
                        "retry required"
                    )

                    self._commit(recovered)

        # Restore the remaining deadline after a restart.
        if self._state["current"] is not None:
            remaining = (
                datetime.fromisoformat(
                    self._state["current"]["deadline_at"]
                )
                - datetime.now(timezone.utc)
            ).total_seconds()

            self._deadline_clock = (
                monotonic() + max(0, remaining)
            )

    def _commit(self, proposed: dict) -> None:
        """Persist first, then expose new state to API callers."""
        if self._store is not None:
            self._store.save(proposed)

        self._state = proposed

    def _check_deadline(self) -> None:
        current = self._state["current"]

        if (
            current is not None
            and current["status"] == "collecting"
            and (
                datetime.now(timezone.utc)
                >= datetime.fromisoformat(current["deadline_at"])
                or (
                    self._deadline_clock is not None
                    and monotonic() >= self._deadline_clock
                )
            )
        ):
            proposed = deepcopy(self._state)
            proposed["current"]["status"] = "deadline_reached"
            self._commit(proposed)

    def _summary(self) -> dict:
        state = self._state

        return {
            **deepcopy(state["current"]),
            "participants": list(state["participants"]),
            "submissions_received": len(state["updates"]),
            "submitted_clients": sorted(state["updates"]),
            "current_model_version": state["model_version"],
        }

    async def register(self, client_id: str) -> dict:
        async with self._lock:
            if client_id in self._state["registered_clients"]:
                raise ValueError("Client already registered")

            proposed = deepcopy(self._state)
            proposed["registered_clients"].append(client_id)
            proposed["registered_clients"].sort()

            self._commit(proposed)

            return {
                "client_id": client_id,
                "status": "registered",
            }

    async def clients(self) -> dict:
        async with self._lock:
            clients = list(self._state["registered_clients"])

            return {
                "clients": clients,
                "count": len(clients),
            }

    async def model(self) -> dict:
        async with self._lock:
            return {
                "model_version": self._state["model_version"],
                "parameters": list(
                    self._state["model_parameters"]
                ),
            }

    async def start(
        self,
        deadline_seconds: int,
        participants: set[str] | None = None,
    ) -> dict:
        if not 1 <= deadline_seconds <= 3600:
            raise ValueError(
                "Deadline must be between 1 and 3600 seconds"
            )

        async with self._lock:
            self._check_deadline()
            current = self._state["current"]

            if (
                current is not None
                and current["status"] not in {
                    "completed",
                    "skipped_insufficient_updates",
                }
            ):
                raise ValueError(
                    "A round already exists; "
                    "it must be finalised first"
                )

            proposed = deepcopy(self._state)
            started = datetime.now(timezone.utc)

            proposed["current"] = {
                "round_id": proposed["next_round_id"],
                "model_version": proposed["model_version"],
                "status": "collecting",
                "started_at": started.isoformat(),
                "deadline_at": (
                    started + timedelta(
                        seconds=deadline_seconds
                    )
                ).isoformat(),
            }

            proposed["next_round_id"] += 1

            proposed["participants"] = sorted(
                participants
                if participants is not None
                else proposed["registered_clients"]
            )

            proposed["updates"] = {}

            self._commit(proposed)
            self._deadline_clock = (
                monotonic() + deadline_seconds
            )

            return self._summary()

    async def current(self) -> dict | None:
        async with self._lock:
            self._check_deadline()

            return (
                self._summary()
                if self._state["current"]
                else None
            )

    async def submit(
        self,
        *,
        client_id: str,
        round_id: int,
        model_version: int,
        sample_count: int,
        parameters: list[float],
    ) -> dict:
        async with self._lock:
            self._check_deadline()

            state = self._state
            current = state["current"]

            if current is None:
                raise ValueError("No training round exists")

            if round_id != current["round_id"]:
                raise ValueError(
                    "Update belongs to a different round"
                )

            if model_version != current["model_version"]:
                raise ValueError(
                    "Update uses an incorrect model version"
                )

            if current["status"] != "collecting":
                raise ValueError(
                    "Round is no longer collecting updates"
                )

            if client_id not in state["participants"]:
                raise ValueError(
                    "Client is not participating in this round"
                )

            if client_id in state["updates"]:
                raise ValueError(
                    "Client already submitted an update for this round"
                )

            if sample_count < 1:
                raise ValueError(
                    "Sample count must be positive"
                )

            if len(parameters) != len(state["model_parameters"]):
                raise ValueError(
                    "Update parameter count does not match global model"
                )

            if not all(
                math.isfinite(value)
                for value in parameters
            ):
                raise ValueError(
                    "Update contains non-finite parameter values"
                )

            proposed = deepcopy(state)

            proposed["updates"][client_id] = {
                "sample_count": sample_count,
                "parameters": list(parameters),
            }

            self._commit(proposed)

            return {
                "client_id": client_id,
                "round_id": round_id,
                "status": "received_unvalidated",
                "submissions_received": len(
                    proposed["updates"]
                ),
            }

    async def close(self) -> dict:
        async with self._lock:
            self._check_deadline()

            state = self._state
            current = state["current"]

            if current is None:
                raise ValueError("No training round exists")

            if current["status"] not in {
                "collecting",
                "deadline_reached",
            }:
                raise ValueError(
                    "Round has already been closed"
                )

            if (
                current["status"] == "collecting"
                and len(state["updates"])
                < len(state["participants"])
            ):
                raise ValueError(
                    "Cannot close before the deadline "
                    "while clients are pending"
                )

            proposed = deepcopy(state)

            proposed["current"]["closed_at"] = (
                datetime.now(timezone.utc).isoformat()
            )

            if len(proposed["updates"]) < 3:
                proposed["current"]["status"] = (
                    "skipped_insufficient_updates"
                )
                proposed["current"]["accepted_clients"] = []
                proposed["current"]["rejected_clients"] = []
            else:
                proposed["current"]["status"] = (
                    "awaiting_validation"
                )

            self._commit(proposed)
            return self._summary()

    @staticmethod
    def _verify_result(result, updates, dimensions):
        if not isinstance(result, AggregationResult):
            raise ValueError(
                "Invalid aggregation result type"
            )

        accepted = result.accepted_clients
        rejected = result.rejected_clients

        if (
            len(accepted) != len(set(accepted))
            or len(rejected) != len(set(rejected))
            or set(accepted) & set(rejected)
            or set(accepted) | set(rejected) != set(updates)
        ):
            raise ValueError(
                "Inconsistent accepted/rejected client IDs"
            )

        if len(accepted) < 3:
            if result.parameters is not None:
                raise ValueError(
                    "Unexpected parameters with fewer "
                    "than 3 accepted updates"
                )

        elif (
            result.parameters is None
            or len(result.parameters) != dimensions
            or not all(
                math.isfinite(x)
                for x in result.parameters
            )
        ):
            raise ValueError(
                "Invalid aggregated model"
            )

    async def finalize(self, aggregator) -> dict:
        # Phase 1: Save the aggregation-in-progress marker.
        async with self._lock:
            current = self._state["current"]

            if (
                current is None
                or current["status"] not in {
                    "awaiting_validation",
                    "aggregation_failed",
                }
            ):
                raise ValueError(
                    "Round is not ready for aggregation"
                )

            proposed = deepcopy(self._state)
            proposed["current"]["status"] = "aggregating"

            self._commit(proposed)

            round_id = current["round_id"]
            model_version = current["model_version"]
            base_model = list(
                self._state["model_parameters"]
            )
            updates = deepcopy(self._state["updates"])

        try:
            # Run aggregation without holding the coordinator lock.
            result = await aggregator.aggregate(
                round_id=round_id,
                model_version=model_version,
                current_parameters=base_model,
                updates=updates,
            )

            self._verify_result(
                result,
                updates,
                len(base_model),
            )

        except BaseException as exc:
            async with self._lock:
                if (
                    self._state["current"] is not None
                    and self._state["current"]["round_id"]
                    == round_id
                    and self._state["current"]["status"]
                    == "aggregating"
                ):
                    proposed = deepcopy(self._state)

                    proposed["current"]["status"] = (
                        "aggregation_failed"
                    )

                    self._commit(proposed)

            if isinstance(
                exc,
                (
                    asyncio.CancelledError,
                    KeyboardInterrupt,
                    SystemExit,
                ),
            ):
                raise

            raise AggregationFailure(
                "Aggregation failed; global model unchanged"
            ) from exc

        # Phase 2: Publish model, version and completion atomically.
        async with self._lock:
            current = self._state["current"]

            if (
                current is None
                or current["round_id"] != round_id
                or current["status"] != "aggregating"
                or self._state["model_version"]
                != model_version
            ):
                raise AggregationFailure(
                    "Round changed during aggregation"
                )

            proposed = deepcopy(self._state)

            proposed["current"]["accepted_clients"] = sorted(
                result.accepted_clients
            )
            proposed["current"]["rejected_clients"] = sorted(
                result.rejected_clients
            )

            proposed["current"]["finalized_at"] = (
                datetime.now(timezone.utc).isoformat()
            )

            if len(result.accepted_clients) < 3:
                proposed["current"]["status"] = (
                    "skipped_insufficient_updates"
                )
            else:
                proposed["model_parameters"] = list(
                    result.parameters
                )
                proposed["model_version"] += 1
                proposed["current"]["status"] = "completed"

            self._commit(proposed)
            return self._summary()
