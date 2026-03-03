"""Abstract cache port."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class CachePort(ABC):
    """Port (interface) for cache adapters."""

    @abstractmethod
    async def get(self, key: str) -> Any | None:
        """Get a value by key. Returns None if not found."""

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set a value with an optional TTL in seconds."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete a key."""

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if a key exists."""

    @abstractmethod
    async def increment(self, key: str, ttl: int | None = None) -> int:
        """Atomically increment a counter and return the new value."""

    @abstractmethod
    async def expire(self, key: str, ttl: int) -> None:
        """Set TTL on an existing key."""

    @abstractmethod
    async def flush_pattern(self, pattern: str) -> int:
        """Delete all keys matching a glob pattern. Returns count deleted."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Ping the cache backend."""