
"""SQLite snapshot storage for one TrustFed coordinator process.

The single JSON snapshot is committed atomically. This is a local-disk
prototype, NOT a shared-store or leader-election implementation.
"""

import json
import sqlite3
from contextlib import closing
from pathlib import Path


class SQLiteStateStore:
    def __init__(self, path: str):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)

        with closing(sqlite3.connect(self.path, timeout=5)) as connection:
            with connection:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS coordinator_state "
                    "(id INTEGER PRIMARY KEY CHECK(id = 1), payload TEXT NOT NULL)"
                )

    def load(self) -> dict | None:
        with closing(sqlite3.connect(self.path, timeout=5)) as connection:
            row = connection.execute(
                "SELECT payload FROM coordinator_state WHERE id = 1"
            ).fetchone()

        return json.loads(row[0]) if row else None

    def save(self, state: dict) -> None:
        payload = json.dumps(
            state,
            allow_nan=False,
            separators=(",", ":"),
        )

        with closing(sqlite3.connect(self.path, timeout=5)) as connection:
            with connection:
                connection.execute(
                    "INSERT INTO coordinator_state (id, payload) VALUES (1, ?) "
                    "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                    (payload,),
                )
