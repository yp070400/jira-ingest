"""Shared FastAPI dependency providers."""
from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.llm.embedding_adapters import (
    get_embedding_adapter,
    get_jira_adapter,
    get_llm_adapter,
)
from app.application.services.analysis_service import AnalysisService
from app.application.services.embedding_service import EmbeddingService
from app.application.services.feedback_service import FeedbackService
from app.application.services.ingestion_service import IngestionService
from app.application.services.search_service import SearchService
from app.infrastructure.cache.redis_client import RedisCache, get_redis_client
from app.infrastructure.database.session import get_db_session
from app.infrastructure.vector_store.faiss_store import FAISSVectorStore
from app.repositories.audit_repository import AuditRepository
from app.repositories.embedding_repository import EmbeddingRepository
from app.repositories.feedback_repository import FeedbackRepository
from app.repositories.reranking_repository import RerankingRepository
from app.repositories.ticket_repository import TicketRepository
from app.repositories.user_repository import UserRepository

# ── Singleton store (set once at startup) ─────────────────────────────────────

_vector_store: FAISSVectorStore | None = None


def set_vector_store(store: FAISSVectorStore) -> None:
    global _vector_store
    _vector_store = store


def get_vector_store() -> FAISSVectorStore:
    if _vector_store is None:
        raise RuntimeError("Vector store not initialized — app startup incomplete")
    return _vector_store


# ── Per-request DB session ─────────────────────────────────────────────────────

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_db_session():
        yield session


# ── Cache ──────────────────────────────────────────────────────────────────────

def get_cache() -> RedisCache:
    return RedisCache(get_redis_client())


# ── Service factories ──────────────────────────────────────────────────────────

async def get_embedding_service(
    session: AsyncSession = Depends(get_session),
) -> EmbeddingService:
    return EmbeddingService(
        embedding_adapter=get_embedding_adapter(),
        vector_store=get_vector_store(),
        embedding_repo=EmbeddingRepository(session),
        ticket_repo=TicketRepository(session),
    )


async def get_search_service(
    session: AsyncSession = Depends(get_session),
) -> SearchService:
    return SearchService(
        vector_store=get_vector_store(),
        ticket_repo=TicketRepository(session),
        reranking_repo=RerankingRepository(session),
    )


async def get_analysis_service(
    session: AsyncSession = Depends(get_session),
) -> AnalysisService:
    vs = get_vector_store()
    embedding_svc = EmbeddingService(
        embedding_adapter=get_embedding_adapter(),
        vector_store=vs,
        embedding_repo=EmbeddingRepository(session),
        ticket_repo=TicketRepository(session),
    )
    search_svc = SearchService(
        vector_store=vs,
        ticket_repo=TicketRepository(session),
        reranking_repo=RerankingRepository(session),
    )
    return AnalysisService(
        embedding_service=embedding_svc,
        search_service=search_svc,
        llm_adapter=get_llm_adapter(),
        cache=get_cache(),
        audit_repo=AuditRepository(session),
    )


async def get_feedback_service(
    session: AsyncSession = Depends(get_session),
) -> FeedbackService:
    return FeedbackService(
        feedback_repo=FeedbackRepository(session),
        reranking_repo=RerankingRepository(session),
    )


async def get_ingestion_service(
    session: AsyncSession = Depends(get_session),
) -> IngestionService:
    vs = get_vector_store()
    embedding_svc = EmbeddingService(
        embedding_adapter=get_embedding_adapter(),
        vector_store=vs,
        embedding_repo=EmbeddingRepository(session),
        ticket_repo=TicketRepository(session),
    )
    return IngestionService(
        jira_adapter=get_jira_adapter(),
        ticket_repo=TicketRepository(session),
        embedding_service=embedding_svc,
    )