"""Feedback endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_feedback_service
from app.application.dto.feedback_dto import (
    FeedbackRequest,
    FeedbackStatsResponse,
    WeightsResponse,
)
from app.application.services.feedback_service import FeedbackService
from app.infrastructure.database.session import get_db_session
from app.observability.logger import get_logger
from app.repositories.feedback_repository import FeedbackRepository
from app.repositories.reranking_repository import RerankingRepository
from app.security.rbac import CurrentUser, RequireAdmin, RequireUser, get_current_user

router = APIRouter(prefix="/feedback", tags=["feedback"])
logger = get_logger(__name__)


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    body: FeedbackRequest,
    current_user: CurrentUser = Depends(RequireUser),
    feedback_svc: FeedbackService = Depends(get_feedback_service),
) -> dict:
    """Submit feedback for an AI suggestion."""
    return await feedback_svc.submit_feedback(body, reviewer_id=current_user.user_id)


@router.get("/stats", response_model=FeedbackStatsResponse)
async def get_feedback_stats(
    current_user: CurrentUser = Depends(get_current_user),
    feedback_svc: FeedbackService = Depends(get_feedback_service),
) -> FeedbackStatsResponse:
    if not current_user.is_reviewer_or_above():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Reviewer or Admin role required",
        )
    return await feedback_svc.get_stats()


@router.get("/weights", response_model=WeightsResponse)
async def get_reranking_weights(
    current_user: CurrentUser = Depends(RequireAdmin),
    session: AsyncSession = Depends(get_db_session),
) -> WeightsResponse:
    reranking_repo = RerankingRepository(session)
    feedback_repo = FeedbackRepository(session)
    weights = await reranking_repo.get_all_weights()
    stats = await feedback_repo.get_global_stats()
    return WeightsResponse(weights=weights, feedback_count=stats["total_feedback"])


@router.post("/aggregate", response_model=dict)
async def trigger_aggregation(
    current_user: CurrentUser = Depends(RequireAdmin),
    feedback_svc: FeedbackService = Depends(get_feedback_service),
) -> dict:
    """Manually trigger feedback aggregation. Admin only."""
    result = await feedback_svc.aggregate_and_update_weights()
    logger.info("Manual feedback aggregation triggered", user=current_user.email)
    return result