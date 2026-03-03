"""Background feedback aggregation worker."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def run_feedback_aggregation() -> None:
    """Scheduled feedback aggregation and reranking weight update."""
    from app.infrastructure.database.session import get_session_factory
    from app.repositories.feedback_repository import FeedbackRepository
    from app.repositories.reranking_repository import RerankingRepository
    from app.application.services.feedback_service import FeedbackService

    logger.info("Background feedback aggregation: starting")
    factory = get_session_factory()

    async with factory() as session:
        feedback_repo = FeedbackRepository(session)
        reranking_repo = RerankingRepository(session)
        feedback_svc = FeedbackService(feedback_repo, reranking_repo)
        result = await feedback_svc.aggregate_and_update_weights()
        await session.commit()

    logger.info("Background feedback aggregation complete: %s", result)