from __future__ import annotations

import hashlib
import time
from typing import Protocol

from redis.asyncio import Redis


class SessionStore(Protocol):
    async def initialize(self) -> None: ...

    async def revoke_token(self, jti: str, ttl: int) -> None: ...

    async def is_token_revoked(self, jti: str) -> bool: ...

    async def failure_count(self, key: str) -> int: ...

    async def record_failure(self, key: str, window: int) -> int: ...

    async def clear_failures(self, key: str) -> None: ...

    async def close(self) -> None: ...


def _failure_key(key: str) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return f"auth:fail:{digest}"


class RedisSessionStore:
    def __init__(self, redis_url: str) -> None:
        self.redis = Redis.from_url(redis_url, decode_responses=True)

    async def initialize(self) -> None:
        await self.redis.ping()

    async def revoke_token(self, jti: str, ttl: int) -> None:
        await self.redis.setex(f"auth:revoked:{jti}", max(1, ttl), "1")

    async def is_token_revoked(self, jti: str) -> bool:
        return bool(await self.redis.exists(f"auth:revoked:{jti}"))

    async def failure_count(self, key: str) -> int:
        value = await self.redis.get(_failure_key(key))
        return int(value or 0)

    async def record_failure(self, key: str, window: int) -> int:
        redis_key = _failure_key(key)
        async with self.redis.pipeline(transaction=True) as pipeline:
            pipeline.incr(redis_key)
            pipeline.expire(redis_key, window, nx=True)
            result = await pipeline.execute()
        return int(result[0])

    async def clear_failures(self, key: str) -> None:
        await self.redis.delete(_failure_key(key))

    async def close(self) -> None:
        await self.redis.aclose()


class MemorySessionStore:
    def __init__(self) -> None:
        self.revoked_tokens: dict[str, float] = {}
        self.failures: dict[str, tuple[int, float]] = {}

    async def initialize(self) -> None:
        return None

    async def revoke_token(self, jti: str, ttl: int) -> None:
        self.revoked_tokens[jti] = time.time() + ttl

    async def is_token_revoked(self, jti: str) -> bool:
        expires_at = self.revoked_tokens.get(jti)
        if expires_at is None:
            return False
        if expires_at <= time.time():
            self.revoked_tokens.pop(jti, None)
            return False
        return True

    async def failure_count(self, key: str) -> int:
        item = self.failures.get(_failure_key(key))
        if item is None or item[1] <= time.time():
            self.failures.pop(_failure_key(key), None)
            return 0
        return item[0]

    async def record_failure(self, key: str, window: int) -> int:
        storage_key = _failure_key(key)
        count = await self.failure_count(key) + 1
        self.failures[storage_key] = (count, time.time() + window)
        return count

    async def clear_failures(self, key: str) -> None:
        self.failures.pop(_failure_key(key), None)

    async def close(self) -> None:
        self.revoked_tokens.clear()
        self.failures.clear()

