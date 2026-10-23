
import asyncio
import math
from datetime import datetime, timedelta, timezone
from time import monotonic


class RoundManager:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._current = None
        self._round_number = 1
        self._model_version = 0
        self._deadline_clock = None

        # Clients selected at the start of the active round.
        self._participants = set()

        # Received updates are not yet TrustFed-validated.
        self._updates = {}

    def _update_deadline_locked(self):
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
        }

    async def start(self, deadline_seconds: int, participants: set[str]):
        async with self._lock:
            self._update_deadline_locked()

            if (
                self._current is not None
                and self._current["status"]
                not in {"completed", "skipped_insufficient_updates"}
            ):
                raise ValueError(
                    "A round already exists; "
                    "it must be finalised first"
                )

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
            if self._current is None:
                return None
            return self._summary_locked()

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
                raise ValueError(
                    "Client already submitted an update for this round"
                )

            if not all(math.isfinite(value) for value in parameters):
                raise ValueError("Update contains non-finite parameter values")

            # Save the submission for validation by Member 1's component.
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
        """Close update collection; do not treat received updates as valid."""
        async with self._lock:
            self._update_deadline_locked()

            if self._current is None:
                raise ValueError("No training round exists")

            if self._current["status"] not in {
                "collecting", "deadline_reached"
            }:
                raise ValueError("Round has already been closed")

            # Only close early if every participant has submitted.
            if (
                self._current["status"] == "collecting"
                and len(self._updates) < len(self._participants)
            ):
                raise ValueError(
                    "Cannot close before the deadline while clients are pending"
                )

            if len(self._updates) < 3:
                # Three valid updates are impossible with fewer than three received.
                # The model remains unchanged.
                self._current["status"] = "skipped_insufficient_updates"
            else:
                # Member 1 must validate first. Do not publish a new model yet.
                self._current["status"] = "awaiting_validation"

            self._current["closed_at"] = datetime.now(timezone.utc).isoformat()
            return self._summary_locked()
