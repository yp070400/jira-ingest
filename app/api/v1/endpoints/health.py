"""Health and readiness endpoints."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse

from app.infrastructure.cache.redis_client import get_redis_client
from app.infrastructure.database.session import get_engine
from app.observability.metrics import get_metrics_response

router = APIRouter(tags=["health"])


@router.get("/health", include_in_schema=False)
async def health() -> dict:
    """Basic liveness check — returns 200 if the process is alive."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/ready")
async def readiness() -> JSONResponse:
    """
    Deep readiness check.
    Verifies database and Redis connectivity.
    Returns 200 only when all dependencies are reachable.
    """
    checks: dict[str, str] = {}
    all_ok = True

    # Database
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"
        all_ok = False

    # Redis
    try:
        redis = get_redis_client()
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"
        all_ok = False

    status_code = 200 if all_ok else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if all_ok else "not_ready",
            "checks": checks,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    """Prometheus metrics endpoint."""
    data, content_type = get_metrics_response()
    return Response(content=data, media_type=content_type)