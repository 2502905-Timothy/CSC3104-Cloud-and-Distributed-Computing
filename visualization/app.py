"""Optional GUI for TrustFed, with no changes to existing coordinator/client code.

Run from the repository root:
    python -m visualization.app coordinator --port 8500
    python -m visualization.app client --port 8501
Each client instance must run on the computer that owns its training CSV.
"""

import argparse
import asyncio
import csv
import io
import json
import math
import os
import re
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import requests
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from client.train import local_train

UI_PATH = Path(__file__).with_name("ui.html")
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
DEFAULT_STATE_DB = Path.home() / ".trustfed" / "coordinator.sqlite3"


def read_trust_scores(db_path: Path, model_version: int, current_round: dict | None) -> dict:
    """Read real committed trust scores from the SAME coordinator SQLite DB.

    No extra coordinator endpoint or write is needed. This only works when the
    GUI can access the coordinator's local state database. A mismatch is hidden
    instead of displaying unrelated or stale trust scores.
    """
    if not db_path.is_file():
        return {"state": "unavailable", "scores": {}}
    try:
        with sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1) as db:
            row = db.execute(
                "SELECT payload FROM coordinator_state WHERE id = 1"
            ).fetchone()
        if row is None:
            return {"state": "unavailable", "scores": {}}
        saved = json.loads(row[0])
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError):
        return {"state": "unavailable", "scores": {}}

    saved_round = saved.get("current")
    # Match both the model version and specific training round. The latter
    # avoids accidentally reading the database from another local demo.
    if saved.get("model_version") != model_version:
        return {"state": "unavailable", "scores": {}}
    if (current_round is None) != (saved_round is None):
        return {"state": "unavailable", "scores": {}}
    if current_round is not None and (
        current_round.get("round_id") != saved_round.get("round_id")
        or current_round.get("started_at") != saved_round.get("started_at")
    ):
        return {"state": "unavailable", "scores": {}}

    raw = saved.get("trust_scores", {})
    if not isinstance(raw, dict):
        return {"state": "unavailable", "scores": {}}
    scores = {
        client_id: float(score)
        for client_id, score in raw.items()
        if isinstance(client_id, str)
        and isinstance(score, (int, float))
        and not isinstance(score, bool)
        and math.isfinite(score)
        and 0 <= score <= 1
    }
    if len(scores) != len(raw):
        return {"state": "unavailable", "scores": {}}
    return {"state": "ready" if scores else "empty", "scores": scores, "model_version": model_version}


def read_api_trust_scores(url: str, model_version: int) -> dict | None:
    """Fetch committed trust scores through the coordinator HTTP API.

    Returns None only for older coordinator versions lacking this endpoint;
    the caller can then safely try a matching local SQLite snapshot.
    """
    response = api_request("GET", f"{url}/model/trust-scores")
    if response.status_code == 404:
        return None
    if not response.ok:
        return {"state": "unavailable", "scores": {}}
    try:
        payload = response.json()
        if payload.get("model_version") != model_version:
            return {"state": "unavailable", "scores": {}}
        raw = payload.get("trust_scores")
        if not isinstance(raw, dict):
            return {"state": "unavailable", "scores": {}}
        scores = {}
        for client_id, score in raw.items():
            if (
                not isinstance(client_id, str)
                or not isinstance(score, (int, float))
                or isinstance(score, bool)
                or not math.isfinite(score)
                or not 0 <= score <= 1
            ):
                return {"state": "unavailable", "scores": {}}
            scores[client_id] = float(score)
        return {
            "state": "ready" if scores else "empty",
            "scores": scores,
            "model_version": model_version,
        }
    except (ValueError, TypeError, AttributeError):
        return {"state": "unavailable", "scores": {}}


class ConnectRequest(BaseModel):
    client_id: str = Field(min_length=1, max_length=64)
    csv_text: str = Field(min_length=1, max_length=2_000_000)
    epochs: int = Field(default=3, ge=1, le=20)


class StartRequest(BaseModel):
    deadline_seconds: int = Field(default=30, ge=1, le=3600)


def read_dataset(csv_text: str):
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
    columns = reader.fieldnames or []
    text_col = "message" if "message" in columns else "text" if "text" in columns else None
    if text_col is None or "label" not in columns:
        raise ValueError("CSV must contain 'message,label' columns (or 'text,label').")
    texts, labels = [], []
    for row in reader:
        if not row or not any(str(v or "").strip() for v in row.values()):
            continue
        msg = row.get(text_col)
        label = row.get("label")
        if not isinstance(msg, str) or not msg.strip() or str(label).strip() not in ("0", "1"):
            raise ValueError("Each data row needs a nonempty message and label 0 or 1.")
        texts.append(msg)
        labels.append(int(str(label).strip()))
    if not texts:
        raise ValueError("CSV must contain at least one labelled message.")
    return texts, labels


def api_request(method: str, url: str, **kwargs):
    try:
        return requests.request(method, url, timeout=8, **kwargs)
    except requests.RequestException as exc:
        raise ConnectionError(f"Coordinator unreachable: {exc}") from exc


class LocalClient:
    """One GUI process = one local training client; CSV never goes to coordinator."""

    def __init__(self, coordinator_url: str):
        self.url = coordinator_url.rstrip("/")
        self.client_id = None
        self.texts = []
        self.labels = []
        self.epochs = 3
        self.running = False
        self.task = None
        self.status = "disconnected"
        self.round_id = None
        self.last_attempted = 0
        self.events = []
        self.lock = asyncio.Lock()

    def log(self, message: str):
        self.events.insert(0, {
            "at": datetime.now().strftime("%H:%M:%S"),
            "message": message,
        })
        del self.events[15:]

    async def connect(self, request: ConnectRequest):
        if not ID_PATTERN.fullmatch(request.client_id):
            raise HTTPException(400, "Client ID must use letters, numbers, underscores or hyphens.")
        try:
            texts, labels = read_dataset(request.csv_text)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

        async with self.lock:
            if self.running:
                raise HTTPException(409, "This GUI already has a running client. Disconnect first.")
            try:
                response = await asyncio.to_thread(
                    api_request, "POST", f"{self.url}/clients/register",
                    json={"client_id": request.client_id},
                )
            except ConnectionError as exc:
                raise HTTPException(503, str(exc)) from exc
            if response.status_code not in (201, 409):
                raise HTTPException(502, f"Registration failed (HTTP {response.status_code}): {response.text[:180]}")

            self.client_id = request.client_id
            self.texts, self.labels = texts, labels
            self.epochs = request.epochs
            self.status = "waiting"
            self.running = True
            self.last_attempted = 0
            self.round_id = None
            self.log(f"Registered as {self.client_id}; {len(texts)} local messages ready.")
            if response.status_code == 409:
                self.log("ID already existed; continuing as a returning client (no authentication).")
            self.task = asyncio.create_task(self.poll())
            return self.snapshot()

    def snapshot(self):
        return {
            "client_id": self.client_id,
            "registered_gui": self.running,
            "status": self.status,
            "round_id": self.round_id,
            "sample_count": len(self.texts),
            "label_counts": {
                "scam": self.labels.count(1),
                "legitimate": self.labels.count(0),
            },
            "events": list(self.events),
            "coordinator": self.url,
        }

    async def disconnect(self):
        async with self.lock:
            self.running = False
            task = self.task
            self.task = None
            if task is not None:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            self.status = "disconnected"
            self.log("Local client process stopped polling. Registration remains saved by coordinator.")
            return self.snapshot()

    async def poll(self):
        while self.running:
            try:
                response = await asyncio.to_thread(
                    api_request, "GET", f"{self.url}/rounds/current"
                )
                if response.status_code == 404:
                    self.status = "waiting"
                elif response.status_code != 200:
                    raise RuntimeError(f"Round status HTTP {response.status_code}")
                else:
                    info = response.json()
                    round_id = info["round_id"]
                    participants = info.get("participants", [])
                    submitted = info.get("submitted_clients", [])
                    status = info["status"]
                    if (
                        status == "collecting"
                        and round_id > self.last_attempted
                        and self.client_id in participants
                        and self.client_id not in submitted
                    ):
                        await self.train_for_round(info)
                    elif round_id == self.last_attempted and status in (
                        "completed", "skipped_insufficient_updates", "aggregation_failed"
                    ) and self.status not in ("accepted", "rejected", "skipped", "failed"):
                        if status == "completed":
                            self.status = "accepted" if self.client_id in info.get("accepted_clients", []) else "rejected"
                        elif status == "skipped_insufficient_updates":
                            self.status = "skipped"
                        else:
                            self.status = "failed"
                        self.log(f"Round {round_id} ended: {self.status}.")
            except asyncio.CancelledError:
                raise
            except (ConnectionError, requests.RequestException, KeyError, ValueError, RuntimeError) as exc:
                self.status = "connection_error"
                self.log(str(exc)[:180])
            await asyncio.sleep(0.7)

    async def train_for_round(self, info: dict):
        rid = info["round_id"]
        self.round_id = rid
        self.status = "downloading"
        response = await asyncio.to_thread(api_request, "GET", f"{self.url}/model/current")
        if response.status_code != 200:
            raise RuntimeError(f"Model download HTTP {response.status_code}")
        model = response.json()
        if model.get("model_version") != info["model_version"]:
            return  # Retry on next poll if a consistent round is still open.
        self.last_attempted = rid
        self.status = "training"
        self.log(f"Round {rid}: downloaded model v{info['model_version']}; training locally.")
        try:
            parameters = await asyncio.to_thread(
                local_train, model["parameters"], self.texts, self.labels,
                epochs=self.epochs, seed=rid,
            )
            if not self.running:
                return
            self.status = "submitting"
            response = await asyncio.to_thread(
                api_request, "POST", f"{self.url}/updates",
                json={
                    "client_id": self.client_id,
                    "round_id": rid,
                    "model_version": info["model_version"],
                    "sample_count": len(self.texts),
                    "parameters": parameters,
                },
            )
            if response.status_code == 202:
                self.status = "submitted"
                self.log(f"Round {rid}: submitted {len(parameters):,} model parameters (HTTP 202).")
            else:
                self.status = "failed"
                self.log(f"Round {rid}: update rejected (HTTP {response.status_code}).")
        except (Exception,) as exc:
            self.status = "failed"
            self.log(f"Round {rid}: training/submission failed: {str(exc)[:160]}")


def build_app(mode: str, coordinator_url: str, state_db: str | None = None):
    agent = LocalClient(coordinator_url) if mode == "client" else None
    selected_db = Path(
        state_db or os.getenv("TRUSTFED_DB_PATH") or DEFAULT_STATE_DB
    ).expanduser()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            if agent is not None:
                await agent.disconnect()

    app = FastAPI(title=f"TrustFed Visualisation ({mode})", lifespan=lifespan)

    @app.get("/", response_class=HTMLResponse)
    async def index():
        html = UI_PATH.read_text(encoding="utf-8")
        return HTMLResponse(html.replace("__TRUSTFED_MODE__", mode))

    if mode == "coordinator":
        @app.get("/api/status")
        async def status():
            def fetch():
                h = api_request("GET", f"{coordinator_url}/health")
                c = api_request("GET", f"{coordinator_url}/clients")
                r = api_request("GET", f"{coordinator_url}/rounds/current")
                m = api_request("GET", f"{coordinator_url}/model/current")
                for response in (h, c, m):
                    if not response.ok:
                        raise RuntimeError(f"Coordinator HTTP {response.status_code}")
                if r.status_code not in (200, 404):
                    raise RuntimeError(f"Round HTTP {r.status_code}")
                model = m.json()
                current_round = r.json() if r.status_code == 200 else None
                trust = {"state": "not_trustfed", "scores": {}}
                if h.json().get("aggregation_mode") == "trustfed":
                    trust = read_api_trust_scores(coordinator_url, model["model_version"])
                    if trust is None:
                        # Backward compatibility for existing local deployments.
                        trust = read_trust_scores(
                            selected_db, model["model_version"], current_round,
                        )
                return {
                    "health": h.json(),
                    "clients": c.json()["clients"],
                    "round": current_round,
                    "model_version": model["model_version"],
                    "model_size": len(model["parameters"]),
                    "trust": trust,
                }
            try:
                return await asyncio.to_thread(fetch)
            except (ConnectionError, RuntimeError, requests.RequestException) as exc:
                raise HTTPException(503, str(exc)) from exc

        @app.post("/api/start")
        async def start(request: StartRequest):
            try:
                response = await asyncio.to_thread(
                    api_request, "POST", f"{coordinator_url}/rounds/start",
                    json={"deadline_seconds": request.deadline_seconds},
                )
            except ConnectionError as exc:
                raise HTTPException(503, str(exc)) from exc
            if response.status_code != 201:
                raise HTTPException(response.status_code, response.text[:250])
            return response.json()

    else:
        @app.get("/api/status")
        async def status():
            return agent.snapshot()

        @app.post("/api/connect")
        async def connect(request: ConnectRequest):
            return await agent.connect(request)

        @app.post("/api/disconnect")
        async def disconnect():
            return await agent.disconnect()

    return app


def main():
    parser = argparse.ArgumentParser(description="Standalone optional TrustFed visualisation")
    parser.add_argument("mode", choices=("client", "coordinator"))
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--coordinator-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--state-db", default=None,
        help="Coordinator SQLite path for read-only trust scores (defaults to TRUSTFED_DB_PATH)",
    )
    args = parser.parse_args()
    port = args.port or (8500 if args.mode == "coordinator" else 8501)
    print(f"{args.mode.title()} GUI: http://127.0.0.1:{port}")
    uvicorn.run(build_app(args.mode, args.coordinator_url, args.state_db), host=args.host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
