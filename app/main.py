"""
JIRA Resolution Intelligence Tool — FastAPI application entry point.
Handles lifespan: DB init, FAISS load, scheduler start.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.middleware import RequestContextMiddleware, add_cors_middleware
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.router import api_router
from app.config import get_settings
from app.observability.logger import configure_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown."""
    settings = get_settings()
    configure_logging()
    logger.info(
        "Starting %s v%s (env=%s)",
        settings.app_name,
        settings.app_version,
        settings.app_env,
    )

    # ── Startup ────────────────────────────────────────────────────────────
    # 1. Initialize database tables (via Alembic in production, direct in dev)
    from app.infrastructure.database.session import get_engine
    from app.infrastructure.database.base import Base
    import app.models.user  # noqa: F401 - register models
    import app.models.ticket  # noqa: F401
    import app.models.embedding  # noqa: F401
    import app.models.feedback  # noqa: F401
    import app.models.reranking  # noqa: F401
    import app.models.model_registry  # noqa: F401
    import app.models.audit_log  # noqa: F401

    # 2. Load FAISS vector store
    from app.infrastructure.vector_store.faiss_store import FAISSVectorStore
    from app.api.dependencies import set_vector_store

    vector_store = FAISSVectorStore()
    await vector_store.load()
    set_vector_store(vector_store)
    logger.info("FAISS index loaded: %d vectors", vector_store.count())

    # 3. Initialize reranking weights defaults (idempotent)
    from app.infrastructure.database.session import get_session_factory
    from app.repositories.reranking_repository import RerankingRepository

    factory = get_session_factory()
    async with factory() as session:
        reranking_repo = RerankingRepository(session)
        for feature, default_weight in [
            ("similarity", settings.reranking_similarity_weight),
            ("recency", settings.reranking_recency_weight),
            ("feedback", settings.reranking_feedback_weight),
            ("quality", settings.reranking_quality_weight),
        ]:
            existing = await reranking_repo.get_by_feature(feature)
            if not existing:
                await reranking_repo.upsert_weight(feature, default_weight)
        await session.commit()
    logger.info("Reranking weights initialized")

    # 4. Start background scheduler
    from app.infrastructure.scheduler.background_scheduler import start_scheduler
    from app.workers.ingestion_worker import run_incremental_sync
    from app.workers.feedback_worker import run_feedback_aggregation
    from app.workers.embedding_worker import run_embedding_health_check

    scheduler = start_scheduler(
        ingestion_fn=run_incremental_sync,
        feedback_aggregation_fn=run_feedback_aggregation,
        embedding_health_fn=run_embedding_health_check,
    )
    logger.info("Application startup complete")

    # ── Application runs here ────────────────────────────────────────────
    yield

    # ── Shutdown ───────────────────────────────────────────────────────────
    logger.info("Application shutting down...")

    from app.infrastructure.scheduler.background_scheduler import stop_scheduler
    await stop_scheduler()

    # Persist FAISS index only if it was modified since startup
    if vector_store._dirty:
        await vector_store.persist()
        logger.info("FAISS index persisted on shutdown")
    else:
        logger.info("FAISS index unchanged, skipping shutdown persist")

    from app.infrastructure.database.session import close_engine
    await close_engine()

    from app.infrastructure.cache.redis_client import close_redis_pool
    await close_redis_pool()

    logger.info("Application shutdown complete")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Enterprise AI-powered JIRA Resolution Intelligence Tool.\n\n"
            "Ingest resolved JIRA tickets, generate semantic embeddings, "
            "perform vector similarity search, and suggest AI-powered resolutions "
            "for new issues using Quick and Deep analysis modes."
        ),
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        openapi_url="/openapi.json" if settings.debug else None,
        lifespan=lifespan,
    )

    # ── Middleware ─────────────────────────────────────────────────────────
    add_cors_middleware(app)
    app.add_middleware(RequestContextMiddleware)

    # ── Exception Handlers ─────────────────────────────────────────────────
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request, exc):
        return JSONResponse(
            status_code=422,
            content={
                "error": "validation_error",
                "detail": exc.errors(),
                "message": "Request validation failed",
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def custom_http_exception_handler(request, exc):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": "http_error", "detail": exc.detail, "status": exc.status_code},
        )

    # ── Routers ────────────────────────────────────────────────────────────
    app.include_router(health_router)   # /health, /ready, /metrics
    app.include_router(api_router)      # /api/v1/*

    return app


app = create_app()