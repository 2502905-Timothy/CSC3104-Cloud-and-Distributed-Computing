
"""FastAPI coordinator for TrustFed (development stage)."""

import asyncio
import os
from contextlib import asynccontextmanager

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
    deadline_seconds: int = Field(default=30, ge=1, le=3600)


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


# Temporary in-memory state. Single-process use only.
registered_clients: set[str] = set()
clients_lock = asyncio.Lock()
round_manager = RoundManager()

# Mock aggregation is for local coordinator testing only.
if os.getenv("TRUSTFED_MOCK_AGGREGATION") == "1":
    rejection_list = os.getenv(
        "TRUSTFED_MOCK_REJECT_CLIENTS", ""
    )
    aggregator = MockAggregationAdapter(
        rejected_clients=[
            item.strip()
            for item in rejection_list.split(",")
            if item.strip()
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
    yield
    await deadline_worker.stop()


app = FastAPI(
    title="TrustFed Coordinator",
    version="0.3.0",
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
    async with clients_lock:
        if request.client_id in registered_clients:
            raise HTTPException(
                status_code=409,
                detail="Client already registered",
            )

        registered_clients.add(request.client_id)

    return {
        "client_id": request.client_id,
        "status": "registered",
    }


@app.get("/clients")
async def list_clients():
    async with clients_lock:
        ids = sorted(registered_clients)

    return {
        "clients": ids,
        "count": len(ids),
    }


@app.get("/model/current")
async def current_model():
    return await round_manager.model()


@app.post("/rounds/start", status_code=201)
async def start_round(request: StartRoundRequest):
    async with clients_lock:
        participants = set(registered_clients)

    try:
        info = await round_manager.start(
            request.deadline_seconds,
            participants,
        )

        # Arrange automatic processing at the deadline.
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
    # Manual development control, retained for testing.
    try:
        return await round_manager.close()

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@app.post("/rounds/finalize")
async def finalize_round():
    # Manual development control, retained for testing.
    if aggregator is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Aggregation unavailable: configure Role 1 "
                "adapter or opt into mock mode"
            ),
        )

    try:
        return await round_manager.finalize(aggregator)

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
