"""Redis-based sliding window rate limiter."""
from __future__ import annotations

import time
from typing import Callable

from fastapi import Depends, HTTPException, Request, status

from app.config import get_settings
from app.domain.exceptions.domain_exceptions import RateLimitExceededError
from app.infrastructure.cache.redis_client import get_redis_client


async def _rate_limit_check(
    request: Request,
    key_prefix: str,
    limit: int,
    window_seconds: int,
) -> None:
    """Sliding window rate limit check using Redis."""
    client = get_redis_client()
    user_id = getattr(request.state, "user_id", None)
    client_ip = request.client.host if request.client else "unknown"
    identifier = user_id or client_ip
    redis_key = f"rl:{key_prefix}:{identifier}"

    try:
        count = await client.incr(redis_key)
        if count == 1:
            await client.expire(redis_key, window_seconds)
        if count > limit:
            ttl = await client.ttl(redis_key)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "Rate limit exceeded",
                    "limit": limit,
                    "window_seconds": window_seconds,
                    "retry_after": ttl,
                },
                headers={"Retry-After": str(ttl), "X-RateLimit-Limit": str(limit)},
            )
    except HTTPException:
        raise
    except Exception:
        # On Redis failure, allow through (fail open)
        pass


def rate_limit(limit: int | None = None, window: int | None = None, key: str = "default"):
    """FastAPI dependency factory for rate limiting."""
    settings = get_settings()
    _limit = limit or settings.rate_limit_requests
    _window = window or settings.rate_limit_window_seconds

    async def _dependency(request: Request) -> None:
        await _rate_limit_check(request, key, _limit, _window)

    return _dependency


def deep_analysis_rate_limit():
    """Stricter rate limit for deep analysis."""
    settings = get_settings()
    return rate_limit(
        limit=settings.rate_limit_deep_requests,
        window=settings.rate_limit_deep_window_seconds,
        key="deep_analysis",
    )