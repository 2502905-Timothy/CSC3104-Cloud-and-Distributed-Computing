
"""TrustFed Role 3 coordinator; single-process SQLite-backed prototype."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from coordinator.aggregation_adapter import MockAggregationAdapter
from coordinator.deadline_worker import DeadlineWorker
from coordinator.round_manager import AggregationFailure, RoundManager


class ClientRegistration(BaseModel):
    client_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
    )


class StartRoundRequest(BaseModel):
    deadline_seconds: int = Field(
        default=30,
        ge=1,
        le=3600,
    )


class ModelUpdateRequest(BaseModel):
    client_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    round_id: int = Field(ge=1)
    model_version: int = Field(ge=0)
    sample_count: int = Field(ge=1)
    parameters: list[float] = Field(
        min_length=1,
        max_length=20000,
    )


# Store coordinator state outside the Git repository.
DB_PATH = os.getenv(
    "TRUSTFED_DB_PATH",
    str(
        Path.home()
        / ".trustfed"
        / "coordinator.sqlite3"
    ),
)

round_manager = RoundManager(
    db_path=DB_PATH
)

# Mock aggregation is for development testing only.
if os.getenv("TRUSTFED_MOCK_AGGREGATION") == "1":
    names = os.getenv(
        "TRUSTFED_MOCK_REJECT_CLIENTS", ""
    )

    aggregator = MockAggregationAdapter(
        rejected_clients=[
            x.strip()
            for x in names.split(",")
            if x.strip()
        ]
    )
else:
    aggregator = None

deadline_worker = DeadlineWorker(
    round_manager,
    aggregator,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Restore the deadline timer when the server starts.
    info = await round_manager.current()

    if (
        info is not None
        and info["status"] in {
            "collecting",
            "deadline_reached",
            "awaiting_validation",
        }
    ):
        remaining = max(
            0.0,
            (
                datetime.fromisoformat(
                    info["deadline_at"]
                )
                - datetime.now(timezone.utc)
            ).total_seconds(),
        )

        deadline_worker.schedule(
            info["round_id"],
            remaining,
        )

    try:
        yield
    finally:
        await deadline_worker.stop()


app = FastAPI(
    title="TrustFed Coordinator",
    version="0.4.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "coordinator",
        "mock_aggregation": aggregator is not None,
    }


@app.post("/clients/register", status_code=201)
async def register_client(request: ClientRegistration):
    try:
        return await round_manager.register(
            request.client_id
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@app.get("/clients")
async def list_clients():
    return await round_manager.clients()


@app.get("/model/current")
async def current_model():
    return await round_manager.model()


@app.post("/rounds/start", status_code=201)
async def start_round(request: StartRoundRequest):
    try:
        info = await round_manager.start(
            request.deadline_seconds
        )

        deadline_worker.schedule(
            info["round_id"],
            request.deadline_seconds,
        )

        return info

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@app.get("/rounds/current")
async def current_round():
    result = await round_manager.current()

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="No training round exists",
        )

    return result


@app.post("/updates", status_code=202)
async def submit_update(request: ModelUpdateRequest):
    try:
        return await round_manager.submit(
            client_id=request.client_id,
            round_id=request.round_id,
            model_version=request.model_version,
            sample_count=request.sample_count,
            parameters=request.parameters,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@app.post("/rounds/close")
async def close_round():
    # Development-only administrative endpoint.
    try:
        return await round_manager.close()

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@app.post("/rounds/finalize")
async def finalize_round():
    # Development-only administrative endpoint.
    if aggregator is None:
        raise HTTPException(
            status_code=503,
            detail="Aggregation adapter unavailable",
        )

    try:
        return await round_manager.finalize(
            aggregator
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    except AggregationFailure as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc
