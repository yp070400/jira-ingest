"""FastAPI middleware: request ID, timing, logging, CORS."""
from __future__ import annotations

import time
import uuid

from fastapi import Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.config import get_settings
from app.observability.logger import bind_request_context, clear_request_context, get_logger
from app.observability.metrics import http_request_duration_seconds, http_requests_total

logger = get_logger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attaches request ID, measures latency, logs each request."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id
        client_ip = request.client.host if request.client else "unknown"

        bind_request_context(
            request_id=request_id,
            user_id=None,
            ip=client_ip,
        )

        start = time.perf_counter()
        response: Response | None = None
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:
            raise
        finally:
            duration = time.perf_counter() - start
            endpoint = request.url.path
            method = request.method

            http_requests_total.labels(
                method=method,
                endpoint=endpoint,
                status_code=status_code,
            ).inc()
            http_request_duration_seconds.labels(
                method=method,
                endpoint=endpoint,
            ).observe(duration)

            logger.info(
                "http_request",
                method=method,
                path=endpoint,
                status=status_code,
                duration_ms=round(duration * 1000, 2),
                request_id=request_id,
            )
            clear_request_context()


def add_cors_middleware(app: ASGIApp) -> None:
    settings = get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-RateLimit-Limit"],
    )