"""Background embedding health check worker."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def run_embedding_health_check() -> None:
    """Detect stale embeddings and reindex if needed."""
    from app.infrastructure.database.session import get_session_factory
    from app.adapters.llm.embedding_adapters import get_embedding_adapter
    from app.infrastructure.vector_store.faiss_store import FAISSVectorStore
    from app.repositories.ticket_repository import TicketRepository
    from app.repositories.embedding_repository import EmbeddingRepository
    from app.application.services.embedding_service import EmbeddingService
    from app.observability.metrics import scheduler_job_runs_total

    logger.info("Background embedding health check: starting")
    factory = get_session_factory()

    vector_store = FAISSVectorStore()
    await vector_store.load()

    embedding_adapter = get_embedding_adapter()

    async with factory() as session:
        ticket_repo = TicketRepository(session)
        embedding_repo = EmbeddingRepository(session)
        embedding_svc = EmbeddingService(
            embedding_adapter, vector_store, embedding_repo, ticket_repo
        )

        health = await embedding_svc.get_embedding_health()
        logger.info("Embedding health: %s", health)

        # If there are unindexed tickets, process them
        if health["unindexed_count"] > 0:
            logger.info(
                "Processing %d unindexed tickets", health["unindexed_count"]
            )
            unindexed = await ticket_repo.get_unindexed(limit=200)
            for ticket in unindexed:
                try:
                    await embedding_svc.embed_and_index_ticket(ticket.id)
                except Exception as e:
                    logger.error("Failed to index ticket %s: %s", ticket.id, e)

            await vector_store.persist()
            await session.commit()

    scheduler_job_runs_total.labels(
        job_name="embedding_health_check", status="success"
    ).inc()
    logger.info("Background embedding health check complete")