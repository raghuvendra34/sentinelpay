"""Event consumer (Blueprint Phase 4, step 3).

Reads Redis Stream `tx_events` with a consumer group, runs the LangGraph workflow for
DISPUTE_OPENED events, retries 3 times with exponential backoff, then writes the failed
payload to stream `tx_dlq` so no customer dispute is silently dropped.
"""
import asyncio
import logging
import os
import socket
from datetime import datetime, timezone

import redis.asyncio as aioredis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import ResponseError
from redis.exceptions import TimeoutError as RedisTimeoutError

from services.agent_worker.config import REDIS_URL
from services.agent_worker.graph import build_graph, initial_state

STREAM = "tx_events"
DLQ = "tx_dlq"
GROUP = "agent_workers"
CONSUMER = f"{socket.gethostname()}-{os.getpid()}"
MAX_ATTEMPTS = 3
BACKOFF_BASE_SEC = 2  # waits 2s, 4s between attempts
BLOCK_MS = 2000
SOCKET_TIMEOUT_SEC = 30

log = logging.getLogger("agent_worker")


async def ensure_group(r) -> None:
    try:
        await r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def process(r, graph, msg_id: str, fields: dict) -> None:
    if fields.get("event") != "DISPUTE_OPENED":
        # TX_CREATED and any future events: nothing for the agent to do.
        await r.xack(STREAM, GROUP, msg_id)
        return

    last_error = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            await graph.ainvoke(initial_state(fields["tx_id"], fields.get("reason", "")))
            await r.xack(STREAM, GROUP, msg_id)
            log.info("resolved dispute for tx %s (attempt %d)", fields["tx_id"], attempt)
            return
        except Exception as exc:  # noqa: BLE001 - any failure must be retried then dead-lettered
            last_error = f"{type(exc).__name__}: {exc}"
            log.warning("attempt %d/%d failed for tx %s: %s", attempt, MAX_ATTEMPTS, fields.get("tx_id"), last_error)
            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(BACKOFF_BASE_SEC**attempt)

    await r.xadd(
        DLQ,
        {
            **fields,
            "original_message_id": msg_id,
            "error": last_error[:500],
            "failed_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    await r.xack(STREAM, GROUP, msg_id)
    log.error("moved tx %s to %s after %d attempts", fields.get("tx_id"), DLQ, MAX_ATTEMPTS)


async def consume(r, graph) -> None:
    await ensure_group(r)
    # First drain messages delivered to this group but never acknowledged (crash recovery),
    # then switch to new messages only.
    read_id = "0"
    while True:
        try:
            batches = await r.xreadgroup(GROUP, CONSUMER, {STREAM: read_id}, count=10, block=BLOCK_MS)
        except (RedisTimeoutError, RedisConnectionError) as exc:
            log.warning("redis read failed (%s); retrying in 2s", exc)
            await asyncio.sleep(2)
            continue
        entries = batches[0][1] if batches else []
        if read_id == "0" and not entries:
            read_id = ">"
            continue
        for msg_id, fields in entries:
            await process(r, graph, msg_id, fields)


async def _health_server(port: int) -> None:
    """Free hosts such as Render only run web services, which must bind a port."""

    async def handle(reader, writer):
        await reader.read(1024)
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "0.0.0.0", port)
    async with server:
        await server.serve_forever()


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    r = aioredis.from_url(REDIS_URL, decode_responses=True, socket_timeout=SOCKET_TIMEOUT_SEC, health_check_interval=30)
    graph = build_graph()
    tasks = [asyncio.create_task(consume(r, graph))]
    if os.environ.get("PORT"):
        tasks.append(asyncio.create_task(_health_server(int(os.environ["PORT"]))))
    log.info("agent worker %s listening on stream %s", CONSUMER, STREAM)
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
