import uuid

import pytest


@pytest.mark.anyio
async def test_requests_11_and_12_are_rate_limited(client, make_account):
    sender, receiver = await make_account(100_000), await make_account(0)
    codes = []
    for _ in range(12):
        r = await client.post(
            "/api/v1/transfers",
            headers={**client.headers, "Idempotency-Key": str(uuid.uuid4())},
            json={"sender_id": sender, "receiver_id": receiver, "amount_cents": 1},
        )
        codes.append(r.status_code)
    assert codes[:10] == [201] * 10
    assert codes[10:] == [429, 429]
