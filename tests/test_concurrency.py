import asyncio
import uuid

import pytest


@pytest.mark.anyio
async def test_five_simultaneous_400_dollar_transfers_from_1000(client, make_account, balance_of):
    sender, receiver = await make_account(100_000), await make_account(0)

    async def pay():
        return await client.post(
            "/api/v1/transfers",
            headers={**client.headers, "Idempotency-Key": str(uuid.uuid4())},
            json={"sender_id": sender, "receiver_id": receiver, "amount_cents": 40_000},
        )

    results = await asyncio.gather(*[pay() for _ in range(5)])
    ok = [r for r in results if r.status_code == 201]
    failed = [r for r in results if r.status_code == 400]
    assert len(ok) == 2 and len(failed) == 3
    assert all(r.json()["detail"] == "INSUFFICIENT_FUNDS" for r in failed)
    assert await balance_of(sender) == 20_000
    assert await balance_of(receiver) == 80_000
