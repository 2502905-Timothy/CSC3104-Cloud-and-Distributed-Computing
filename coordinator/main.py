
import asyncio

from coordinator.round_manager import RoundManager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(
    title="TrustFed Coordinator",
    version="0.1.0"
)


class ClientRegistration(BaseModel):
    client_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$"
    )


# Temporary storage for registered clients
registered_clients: set[str] = set()
clients_lock = asyncio.Lock()
round_manager = RoundManager()


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "coordinator"
    }


@app.post("/clients/register", status_code=201)
async def register_client(request: ClientRegistration):
    async with clients_lock:
        if request.client_id in registered_clients:
            raise HTTPException(
                status_code=409,
                detail="Client already registered"
            )

        registered_clients.add(request.client_id)

    return {
        "client_id": request.client_id,
        "status": "registered"
    }


@app.get("/clients")
async def list_clients():
    async with clients_lock:
        ids = sorted(registered_clients)

    return {
        "clients": ids,
        "count": len(ids)
    }


class StartRoundRequest(BaseModel):
    deadline_seconds: int = Field(
        default=30,
        ge=1,
        le=3600
    )



@app.post("/rounds/start", status_code=201)
async def start_round(request: StartRoundRequest):
    async with clients_lock:
        participants = set(registered_clients)

    try:
        return await round_manager.start(
            request.deadline_seconds,
            participants
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc)
        ) from exc


@app.get("/rounds/current")
async def current_round():
    result = await round_manager.current()

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="No training round exists"
        )

    return result


class ModelUpdateRequest(BaseModel):
    client_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$"
    )
    round_id: int = Field(ge=1)
    model_version: int = Field(ge=0)
    sample_count: int = Field(ge=1)
    parameters: list[float] = Field(
        min_length=1,
        max_length=20000
    )


@app.post("/updates", status_code=202)
async def submit_update(request: ModelUpdateRequest):
    try:
        return await round_manager.submit(
            client_id=request.client_id,
            round_id=request.round_id,
            model_version=request.model_version,
            sample_count=request.sample_count,
            parameters=request.parameters
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc)
        ) from exc
