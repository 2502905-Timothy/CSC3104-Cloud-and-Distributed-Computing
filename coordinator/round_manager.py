
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

        # Clients participating in this round
        self._participants = set()

        # Model updates received from clients
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

    async def start(
        self,
        deadline_seconds: int,
        participants: set[str]
    ):
        async with self._lock:
            self._update_deadline_locked()

            if self._current is not None:
                raise ValueError(
                    "A round already exists; "
                    "it must be finalised first"
                )

            started = datetime.now(timezone.utc)

            self._deadline_clock = (
                monotonic() + deadline_seconds
            )

            self._participants = set(participants)
            self._updates = {}

            self._current = {
                "round_id": self._round_number,
                "model_version": self._model_version,
                "status": "collecting",
                "started_at": started.isoformat(),
                "deadline_at": (
                    started + timedelta(
                        seconds=deadline_seconds
                    )
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
        parameters: list[float]
    ):
        async with self._lock:
            self._update_deadline_locked()

            if self._current is None:
                raise ValueError(
                    "No training round exists"
                )

            if round_id != self._current["round_id"]:
                raise ValueError(
                    "Update belongs to a different round"
                )

            if model_version != self._current["model_version"]:
                raise ValueError(
                    "Update uses an incorrect model version"
                )

            if self._current["status"] != "collecting":
                raise ValueError(
                    "Round is no longer collecting updates"
                )

            if client_id not in self._participants:
                raise ValueError(
                    "Client is not participating in this round"
                )

            if client_id in self._updates:
                raise ValueError(
                    "Client already submitted an update for this round"
                )

            if not all(
                math.isfinite(value)
                for value in parameters
            ):
                raise ValueError(
                    "Update contains non-finite parameter values"
                )

            # Store the received update.
            # Trust validation happens in Member 1's subsystem.
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
