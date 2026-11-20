import uuid

import pytest
from sqlalchemy import text


@pytest.mark.anyio
async def test_same_idempotency_key_creates_one_transaction(client, make_account, balance_of, db):
    sender, receiver = await make_account(100_000), await make_account(0)
    key = str(uuid.uuid4())
    body = {"sender_id": sender, "receiver_id": receiver, "amount_cents": 2_500}
    headers = {**client.headers, "Idempotency-Key": key}

    first = await client.post("/api/v1/transfers", headers=headers, json=body)
    second = await client.post("/api/v1/transfers", headers=headers, json=body)

    assert first.status_code == 201 and second.status_code == 200
    assert second.headers["Idempotency-Replayed"] == "true"
    assert first.json()["tx_id"] == second.json()["tx_id"]
    assert await balance_of(sender) == 97_500  # charged once

    async with db.connect() as conn:
        entries = (
            await conn.execute(
                text(
                    "SELECT entry_type FROM ledger_entries l JOIN transactions t USING (tx_id) "
                    "WHERE t.idempotency_key = :k ORDER BY entry_type"
                ),
                {"k": key},
            )
        ).scalars().all()
    assert entries == ["CREDIT", "DEBIT"]  # exactly one double-entry pair
