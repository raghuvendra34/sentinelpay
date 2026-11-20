"""API Gateway Service (port 8001).

JWT guard -> sliding-window rate limit -> Idempotency-Key check -> forward to the
Ledger Service -> publish events to the Redis Stream `tx_events`.
"""
import uuid
from contextlib import asynccontextmanager

import httpx
import redis.asyncio as aioredis
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from services.gateway.config import (
    ALLOWED_ORIGINS,
    DATABASE_URL,
    JWT_SECRET,
    LEDGER_URL,
    REDIS_URL,
)
from services.gateway.rate_limiter import is_allowed

STREAM = "tx_events"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    app.state.http = httpx.AsyncClient(timeout=10.0)
    app.state.engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    app.state.sessions = async_sessionmaker(app.state.engine, expire_on_commit=False)
    yield
    await app.state.http.aclose()
    await app.state.redis.aclose()
    await app.state.engine.dispose()


app = FastAPI(title="SentinelPay API Gateway", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Idempotency-Replayed", "Retry-After"],
)

bearer = HTTPBearer(auto_error=False)


async def require_jwt(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    """JWT Auth Guard."""
    if creds is None:
        raise HTTPException(status_code=401, detail="MISSING_TOKEN")
    try:
        return jwt.decode(creds.credentials, JWT_SECRET, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(status_code=401, detail="INVALID_TOKEN")


class TransferIn(BaseModel):
    sender_id: uuid.UUID
    receiver_id: uuid.UUID
    amount_cents: int = Field(gt=0)
    merchant_cat: str = Field(default="P2P_TRANSFER", max_length=50)


class DisputeIn(BaseModel):
    tx_id: uuid.UUID
    reason: str = Field(min_length=3, max_length=500)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "gateway"}


@app.post("/api/v1/transfers")
async def create_transfer(
    payload: TransferIn,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=100),
    _claims: dict = Depends(require_jwt),
):
    redis = app.state.redis

    # Workflow A step 2a: sliding-window rate limit, per account.
    if not await is_allowed(redis, str(payload.sender_id)):
        raise HTTPException(
            status_code=429, detail="RATE_LIMIT_EXCEEDED", headers={"Retry-After": "60"}
        )

    # Workflow A step 2b / Phase 3 step 2: idempotency. Return the stored transaction, never recharge.
    async with app.state.sessions() as session:
        row = (
            await session.execute(
                text("SELECT * FROM transactions WHERE idempotency_key = :k"),
                {"k": idempotency_key},
            )
        ).mappings().first()
    if row:
        return JSONResponse(
            jsonable_encoder(dict(row)), status_code=200, headers={"Idempotency-Replayed": "true"}
        )

    # Phase 3 step 3: forward to the Ledger Service.
    try:
        ledger_resp = await app.state.http.post(
            f"{LEDGER_URL}/internal/transfers",
            json={
                "idempotency_key": idempotency_key,
                "sender_id": str(payload.sender_id),
                "receiver_id": str(payload.receiver_id),
                "amount_cents": payload.amount_cents,
                "merchant_cat": payload.merchant_cat,
            },
        )
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="LEDGER_UNAVAILABLE")

    if ledger_resp.status_code >= 400:
        try:
            detail = ledger_resp.json().get("detail", "LEDGER_ERROR")
        except ValueError:
            detail = "LEDGER_ERROR"
        raise HTTPException(status_code=ledger_resp.status_code, detail=detail)

    tx = ledger_resp.json()

    # Ledger answered 200: a concurrent duplicate resolved to the stored transaction.
    if ledger_resp.status_code == 200:
        return JSONResponse(tx, status_code=200, headers={"Idempotency-Replayed": "true"})

    # Workflow A step 5: async event publish.
    await redis.xadd(STREAM, {"tx_id": tx["tx_id"], "event": "TX_CREATED"})
    if tx["status"] == "FLAGGED":  # amount_cents >= 50000 ($500+): immediate AI inspection
        await redis.xadd(
            STREAM,
            {
                "tx_id": tx["tx_id"],
                "reason": "Auto-flagged: transfer of $500 or more",
                "event": "DISPUTE_OPENED",
            },
        )
    return JSONResponse(tx, status_code=201)


@app.post("/api/v1/disputes", status_code=202)
async def open_dispute(payload: DisputeIn, _claims: dict = Depends(require_jwt)):
    async with app.state.sessions() as session:
        found = (
            await session.execute(
                text("SELECT 1 FROM transactions WHERE tx_id = :t"), {"t": payload.tx_id}
            )
        ).first()
    if not found:
        raise HTTPException(status_code=404, detail="TRANSACTION_NOT_FOUND")

    await app.state.redis.xadd(
        STREAM,
        {"tx_id": str(payload.tx_id), "reason": payload.reason, "event": "DISPUTE_OPENED"},
    )
    return {"status": "accepted", "tx_id": str(payload.tx_id)}


@app.get("/api/v1/accounts/{account_id}/history")
async def account_history(account_id: uuid.UUID, _claims: dict = Depends(require_jwt)):
    """Read-through to the Ledger Service so the console never talks to it directly."""
    try:
        resp = await app.state.http.get(f"{LEDGER_URL}/internal/accounts/{account_id}/history")
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="LEDGER_UNAVAILABLE")
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.json().get("detail", "LEDGER_ERROR"))
    return resp.json()
