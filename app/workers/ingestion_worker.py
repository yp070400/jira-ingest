"""Background ingestion worker — called by APScheduler."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def run_incremental_sync() -> None:
    """
    Scheduled JIRA incremental sync.
    Bootstraps dependencies from the application container.
    """
    from app.infrastructure.database.session import get_session_factory
    from app.adapters.llm.embedding_adapters import get_embedding_adapter, get_jira_adapter
    from app.infrastructure.vector_store.faiss_store import FAISSVectorStore
    from app.repositories.ticket_repository import TicketRepository
    from app.repositories.embedding_repository import EmbeddingRepository
    from app.application.services.embedding_service import EmbeddingService
    from app.application.services.ingestion_service import IngestionService

    logger.info("Background ingestion: starting incremental sync")
    factory = get_session_factory()

    vector_store = FAISSVectorStore()
    await vector_store.load()

    embedding_adapter = get_embedding_adapter()
    jira_adapter = get_jira_adapter()

    async with factory() as session:
        ticket_repo = TicketRepository(session)
        embedding_repo = EmbeddingRepository(session)
        embedding_svc = EmbeddingService(
            embedding_adapter, vector_store, embedding_repo, ticket_repo
        )
        ingestion_svc = IngestionService(jira_adapter, ticket_repo, embedding_svc)
        stats = await ingestion_svc.sync_all_projects(incremental=True)
        await session.commit()

    logger.info("Background ingestion complete: %s", stats)