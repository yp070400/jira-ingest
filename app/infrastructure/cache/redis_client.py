"""Redis cache adapter implementing CachePort."""
from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as aioredis

from app.config import get_settings
from app.domain.interfaces.cache_port import CachePort

logger = logging.getLogger(__name__)

_redis_pool: aioredis.ConnectionPool | None = None


def get_redis_pool() -> aioredis.ConnectionPool:
    global _redis_pool
    if _redis_pool is None:
        settings = get_settings()
        _redis_pool = aioredis.ConnectionPool.from_url(
            settings.redis_url,
            max_connections=settings.redis_max_connections,
            decode_responses=True,
        )
    return _redis_pool


def get_redis_client() -> aioredis.Redis:
    return aioredis.Redis(connection_pool=get_redis_pool())


async def close_redis_pool() -> None:
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.disconnect()
        _redis_pool = None


class RedisCache(CachePort):
    """Redis-backed cache implementation."""

    def __init__(self, client: aioredis.Redis) -> None:
        self._client = client

    async def get(self, key: str) -> Any | None:
        try:
            raw = await self._client.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as exc:
            logger.warning("Cache GET failed for key=%s: %s", key, exc)
            return None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        try:
            serialized = json.dumps(value, default=str)
            if ttl is not None:
                await self._client.setex(key, ttl, serialized)
            else:
                await self._client.set(key, serialized)
        except Exception as exc:
            logger.warning("Cache SET failed for key=%s: %s", key, exc)

    async def delete(self, key: str) -> None:
        try:
            await self._client.delete(key)
        except Exception as exc:
            logger.warning("Cache DELETE failed for key=%s: %s", key, exc)

    async def exists(self, key: str) -> bool:
        try:
            result = await self._client.exists(key)
            return bool(result)
        except Exception as exc:
            logger.warning("Cache EXISTS failed for key=%s: %s", key, exc)
            return False

    async def increment(self, key: str, ttl: int | None = None) -> int:
        try:
            count = await self._client.incr(key)
            if ttl is not None and count == 1:
                await self._client.expire(key, ttl)
            return count
        except Exception as exc:
            logger.warning("Cache INCR failed for key=%s: %s", key, exc)
            return 0

    async def expire(self, key: str, ttl: int) -> None:
        try:
            await self._client.expire(key, ttl)
        except Exception as exc:
            logger.warning("Cache EXPIRE failed for key=%s: %s", key, exc)

    async def flush_pattern(self, pattern: str) -> int:
        try:
            keys = await self._client.keys(pattern)
            if keys:
                return await self._client.delete(*keys)
            return 0
        except Exception as exc:
            logger.warning("Cache FLUSH_PATTERN failed for pattern=%s: %s", pattern, exc)
            return 0

    async def health_check(self) -> bool:
        try:
            response = await self._client.ping()
            return response is True
        except Exception:
            return False