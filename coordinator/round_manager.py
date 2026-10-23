
import asyncio
from datetime import datetime, timedelta, timezone
from time import monotonic


class RoundManager:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._current = None
        self._round_number = 1
        self._model_version = 0
        self._deadline_clock = None

    def _update_deadline_locked(self):
        if (
            self._current is not None
            and self._current["status"] == "collecting"
            and monotonic() >= self._deadline_clock
        ):
            self._current["status"] = "deadline_reached"

    async def start(self, deadline_seconds: int):
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
            return self._current.copy()

    async def current(self):
        async with self._lock:
            self._update_deadline_locked()

            if self._current is None:
                return None

            return self._current.copy()
