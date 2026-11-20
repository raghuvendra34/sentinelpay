"""Unit test for the sliding-window limiter using an in-memory fake Redis (no services needed).

Regression test for the same-millisecond bug: requests sharing a timestamp must each count.
"""
import asyncio

from services.gateway import rate_limiter


class FakePipeline:
    def __init__(self, store):
        self.store, self.ops = store, []

    def zremrangebyscore(self, key, lo, hi):
        self.ops.append(("zrem", key, lo, hi))

    def zadd(self, key, mapping):
        self.ops.append(("zadd", key, mapping))

    def zcard(self, key):
        self.ops.append(("zcard", key))

    def expire(self, key, sec):
        self.ops.append(("expire", key))

    async def execute(self):
        out = []
        for op in self.ops:
            zset = self.store.setdefault(op[1], {})
            if op[0] == "zrem":
                for m in [m for m, s in zset.items() if op[2] <= s <= op[3]]:
                    del zset[m]
                out.append(0)
            elif op[0] == "zadd":
                zset.update(op[2])  # a repeated member overwrites, exactly like Redis
                out.append(len(op[2]))
            elif op[0] == "zcard":
                out.append(len(zset))
            else:
                out.append(True)
        return out


class FakeRedis:
    def __init__(self):
        self.store = {}

    def pipeline(self):
        return FakePipeline(self.store)


def _run_requests(n, frozen_time):
    async def go():
        r = FakeRedis()
        return [await rate_limiter.is_allowed(r, "acct") for _ in range(n)]

    original = rate_limiter.time.time
    rate_limiter.time.time = lambda: frozen_time
    try:
        return asyncio.run(go())
    finally:
        rate_limiter.time.time = original


def test_same_millisecond_requests_are_all_counted():
    results = _run_requests(12, frozen_time=1_700_000_000.123)
    assert results[:10] == [True] * 10
    assert results[10:] == [False, False]
