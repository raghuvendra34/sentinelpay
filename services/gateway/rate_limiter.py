"""Sliding-Window Log Rate Limiter on Redis Sorted Sets (Blueprint Phase 3, step 1)."""
import time
import uuid


async def is_allowed(redis_client, user_id: str, limit: int = 10, window_sec: int = 60) -> bool:
    now_ms = int(time.time() * 1000)
    window_start = now_ms - (window_sec * 1000)
    key = f"rate_limit:{user_id}"
    # The member must be unique per request. With str(now_ms) alone, two requests in the
    # same millisecond share one member, ZADD overwrites instead of adding, and ZCARD
    # undercounts. The score stays the timestamp, so the sliding window is unchanged.
    member = f"{now_ms}:{uuid.uuid4().hex[:8]}"
    pipe = redis_client.pipeline()
    pipe.zremrangebyscore(key, 0, window_start)
    pipe.zadd(key, {member: now_ms})
    pipe.zcard(key)
    pipe.expire(key, window_sec)
    _, _, count, _ = await pipe.execute()
    return count <= limit
