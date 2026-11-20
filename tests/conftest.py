"""Integration-test fixtures. Start Postgres, Redis, Ledger and Gateway first
(`docker compose up --build`), then run `pytest -v`."""
import os
import time
import uuid

import httpx
import pytest
from jose import jwt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from services.gateway.config import DATABASE_URL, JWT_SECRET

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8001")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def auth_headers():
    now = int(time.time())
    token = jwt.encode({"sub": "pytest", "iat": now, "exp": now + 3600}, JWT_SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def client(auth_headers):
    async with httpx.AsyncClient(base_url=GATEWAY_URL, headers=auth_headers, timeout=20.0) as c:
        yield c


@pytest.fixture
async def db():
    engine = create_async_engine(DATABASE_URL)
    yield engine
    await engine.dispose()


@pytest.fixture
def make_account(db):
    """Create a fresh account with a given balance so every test starts from a known state."""

    async def _make(balance_cents: int) -> str:
        account_id = str(uuid.uuid4())
        async with db.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO accounts (account_id, owner_name, email, balance_cents) "
                    "VALUES (:id, 'Test User', :email, :bal)"
                ),
                {"id": account_id, "email": f"{account_id}@test.dev", "bal": balance_cents},
            )
        return account_id

    return _make


@pytest.fixture
def balance_of(db):
    async def _balance(account_id: str) -> int:
        async with db.connect() as conn:
            return (
                await conn.execute(
                    text("SELECT balance_cents FROM accounts WHERE account_id = :id"), {"id": account_id}
                )
            ).scalar_one()

    return _balance
