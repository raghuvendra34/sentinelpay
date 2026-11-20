"""Core Ledger Service (port 8002) - owns financial truth.

Atomic double-entry bookkeeping inside a single PostgreSQL transaction.
Both account rows are locked in deterministic UUID order (SELECT ... ORDER BY
account_id FOR UPDATE) so concurrent transfers can neither overdraw an account
nor deadlock each other.
"""
import json
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from services.ledger.config import DATABASE_URL, FLAG_THRESHOLD_CENTS

# Phase 2, step 1: async SQLAlchemy engine on postgresql+asyncpg://
engine = create_async_engine(DATABASE_URL, pool_size=10, max_overflow=10, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

app = FastAPI(title="SentinelPay Ledger Service", version="1.0.0")


class TransferIn(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=100)
    sender_id: uuid.UUID
    receiver_id: uuid.UUID
    amount_cents: int = Field(gt=0)
    merchant_cat: str = Field(default="P2P_TRANSFER", max_length=50)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ledger"}


async def _tx_by_key(session, key: str):
    row = (
        await session.execute(
            text("SELECT * FROM transactions WHERE idempotency_key = :k"), {"k": key}
        )
    ).mappings().first()
    return dict(row) if row else None


def _replay(existing: dict) -> JSONResponse:
    return JSONResponse(jsonable_encoder(existing), status_code=200)


@app.post("/internal/transfers", status_code=201)
async def create_transfer(payload: TransferIn):
    """Execute one transfer atomically. 201 = created, 200 = idempotent replay."""
    if payload.sender_id == payload.receiver_id:
        raise HTTPException(status_code=400, detail="SAME_ACCOUNT")

    # Phase 2, step 2: sort ids so every transfer locks rows in the same order.
    ids = sorted([payload.sender_id, payload.receiver_id], key=str)

    try:
        async with SessionLocal() as session:
            async with session.begin():
                rows = (
                    await session.execute(
                        text(
                            "SELECT account_id, balance_cents, status FROM accounts "
                            "WHERE account_id = ANY(CAST(:ids AS uuid[])) "
                            "ORDER BY account_id FOR UPDATE"
                        ),
                        {"ids": ids},
                    )
                ).mappings().all()
                accounts = {str(r["account_id"]): r for r in rows}

                # Phase 2, step 3: both accounts exist, are ACTIVE, sender can pay.
                sender = accounts.get(str(payload.sender_id))
                receiver = accounts.get(str(payload.receiver_id))
                if sender is None or receiver is None:
                    raise HTTPException(status_code=404, detail="ACCOUNT_NOT_FOUND")
                if sender["status"] != "ACTIVE" or receiver["status"] != "ACTIVE":
                    raise HTTPException(status_code=400, detail="ACCOUNT_NOT_ACTIVE")

                # Race-safe replay: a concurrent duplicate that waited on our lock
                # lands here after the first request committed.
                existing = await _tx_by_key(session, payload.idempotency_key)
                if existing:
                    return _replay(existing)

                if sender["balance_cents"] < payload.amount_cents:
                    # Raising inside session.begin() rolls the transaction back.
                    raise HTTPException(status_code=400, detail="INSUFFICIENT_FUNDS")

                # Phase 2, step 4: move money.
                await session.execute(
                    text("UPDATE accounts SET balance_cents = balance_cents - :a WHERE account_id = :id"),
                    {"a": payload.amount_cents, "id": payload.sender_id},
                )
                await session.execute(
                    text("UPDATE accounts SET balance_cents = balance_cents + :a WHERE account_id = :id"),
                    {"a": payload.amount_cents, "id": payload.receiver_id},
                )

                status = "FLAGGED" if payload.amount_cents >= FLAG_THRESHOLD_CENTS else "COMPLETED"
                tx = (
                    await session.execute(
                        text(
                            "INSERT INTO transactions "
                            "(idempotency_key, sender_id, receiver_id, amount_cents, merchant_cat, status) "
                            "VALUES (:k, :s, :r, :a, :m, :st) RETURNING *"
                        ),
                        {
                            "k": payload.idempotency_key,
                            "s": payload.sender_id,
                            "r": payload.receiver_id,
                            "a": payload.amount_cents,
                            "m": payload.merchant_cat,
                            "st": status,
                        },
                    )
                ).mappings().one()

                for account_id, entry_type in (
                    (payload.sender_id, "DEBIT"),
                    (payload.receiver_id, "CREDIT"),
                ):
                    await session.execute(
                        text(
                            "INSERT INTO ledger_entries (tx_id, account_id, entry_type, amount_cents) "
                            "VALUES (:t, :acc, :et, :a)"
                        ),
                        {"t": tx["tx_id"], "acc": account_id, "et": entry_type, "a": payload.amount_cents},
                    )
                result = dict(tx)
        return jsonable_encoder(result)

    except IntegrityError:
        # Two identical Idempotency-Keys raced past every earlier check and the
        # UNIQUE constraint caught the loser. Its transaction is already rolled back.
        async with SessionLocal() as session:
            existing = await _tx_by_key(session, payload.idempotency_key)
        if existing:
            return _replay(existing)
        raise


@app.get("/internal/accounts/{account_id}/history")
async def account_history(account_id: uuid.UUID):
    """Balance plus the 15 most recent transactions joined with dispute resolutions."""
    async with SessionLocal() as session:
        acc = (
            await session.execute(
                text("SELECT account_id, owner_name, balance_cents, status FROM accounts WHERE account_id = :id"),
                {"id": account_id},
            )
        ).mappings().first()
        if acc is None:
            raise HTTPException(status_code=404, detail="ACCOUNT_NOT_FOUND")

        rows = (
            await session.execute(
                text(
                    """
                    SELECT t.tx_id, t.sender_id, s.owner_name AS sender_name,
                           t.receiver_id, r.owner_name AS receiver_name,
                           t.amount_cents, t.merchant_cat, t.status, t.risk_score, t.created_at,
                           d.dispute_id, d.reason, d.decision, d.confidence,
                           d.reasoning_trace, d.resolved_at
                    FROM transactions t
                    JOIN accounts s ON s.account_id = t.sender_id
                    JOIN accounts r ON r.account_id = t.receiver_id
                    LEFT JOIN LATERAL (
                        SELECT * FROM dispute_resolutions dr
                        WHERE dr.tx_id = t.tx_id
                        ORDER BY dr.resolved_at DESC LIMIT 1
                    ) d ON TRUE
                    WHERE t.sender_id = :id OR t.receiver_id = :id
                    ORDER BY t.created_at DESC
                    LIMIT 15
                    """
                ),
                {"id": account_id},
            )
        ).mappings().all()

    transactions = []
    for row in rows:
        item = {
            k: row[k]
            for k in (
                "tx_id", "sender_id", "sender_name", "receiver_id", "receiver_name",
                "amount_cents", "merchant_cat", "status", "risk_score", "created_at",
            )
        }
        item["dispute"] = None
        if row["dispute_id"] is not None:
            trace = row["reasoning_trace"]
            if isinstance(trace, str):  # asyncpg returns JSONB as text
                trace = json.loads(trace)
            item["dispute"] = {
                "dispute_id": row["dispute_id"],
                "reason": row["reason"],
                "decision": row["decision"],
                "confidence": row["confidence"],
                "reasoning_trace": trace,
                "resolved_at": row["resolved_at"],
            }
        transactions.append(item)

    return jsonable_encoder({**dict(acc), "transactions": transactions})
