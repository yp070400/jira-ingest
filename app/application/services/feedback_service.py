"""Feedback ingestion and reranking weight adjustment service."""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from app.application.dto.feedback_dto import FeedbackRequest, FeedbackStatsResponse
from app.config import get_settings
from app.observability.metrics import (
    feedback_acceptance_rate,
    feedback_submitted_total,
    rating_to_bucket,
    scheduler_job_runs_total,
)

if TYPE_CHECKING:
    from app.repositories.feedback_repository import FeedbackRepository
    from app.repositories.reranking_repository import RerankingRepository

logger = logging.getLogger(__name__)


class FeedbackService:
    """Handles feedback storage, aggregation, and safe reranking weight updates."""

    def __init__(
        self,
        feedback_repo: "FeedbackRepository",
        reranking_repo: "RerankingRepository",
    ) -> None:
        self._feedback_repo = feedback_repo
        self._reranking_repo = reranking_repo
        self._settings = get_settings()

    async def submit_feedback(
        self, request: FeedbackRequest, reviewer_id: str
    ) -> dict:
        """Persist a feedback record."""
        from app.models.feedback import FeedbackModel

        model = FeedbackModel(
            query_ticket_id=request.query_ticket_id,
            suggested_ticket_id=request.suggested_ticket_id,
            similarity_score=request.similarity_score,
            confidence_score=request.confidence_score,
            model_version=request.model_version,
            embedding_version=request.embedding_version,
            rating=request.rating,
            was_helpful=request.was_helpful,
            was_correct=request.was_correct,
            notes=request.notes,
            reviewer_id=reviewer_id,
        )

        model = await self._feedback_repo.create(model)

        feedback_submitted_total.labels(rating_bucket=rating_to_bucket(request.rating)).inc()

        logger.info(
            "Feedback submitted: ticket=%s rating=%d helpful=%s",
            request.suggested_ticket_id, request.rating, request.was_helpful,
        )

        # Trigger aggregation if we've accumulated enough feedback
        await self._maybe_trigger_aggregation()

        return {"id": model.id, "created_at": model.created_at.isoformat() if model.created_at else None}

    async def aggregate_and_update_weights(self) -> dict:
        """
        Safe learning loop:
        1. Aggregate recent feedback with exponential decay
        2. Compute updated weights
        3. Persist only if enough samples exist
        """
        settings = self._settings
        since = datetime.now(timezone.utc) - timedelta(days=90)

        recent_feedback = await self._feedback_repo.get_recent(since, limit=5000)
        total_count = len(recent_feedback)

        if total_count < settings.feedback_min_samples:
            logger.info(
                "Skipping reranking update: %d samples < minimum %d",
                total_count, settings.feedback_min_samples,
            )
            return {"skipped": True, "reason": "insufficient_samples", "count": total_count}

        # Compute decayed feedback score per ticket
        now = datetime.now(timezone.utc)
        ticket_scores: dict[str, list[float]] = {}

        for fb in recent_feedback:
            if not fb.suggested_ticket_id:
                continue
            if fb.created_at is None:
                continue
            created = fb.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            days_elapsed = (now - created).total_seconds() / 86400
            signal = self._compute_feedback_signal(
                fb.rating, fb.was_helpful, days_elapsed
            )
            if fb.suggested_ticket_id not in ticket_scores:
                ticket_scores[fb.suggested_ticket_id] = []
            ticket_scores[fb.suggested_ticket_id].append(signal)

        # Compute global acceptance rate
        helpful_count = sum(1 for fb in recent_feedback if fb.was_helpful)
        acceptance_rate = helpful_count / total_count if total_count > 0 else 0.0
        feedback_acceptance_rate.set(acceptance_rate)

        # Compute aggregate feedback weight (normalized mean signal)
        all_signals = [s for signals in ticket_scores.values() for s in signals]
        mean_signal = sum(all_signals) / len(all_signals) if all_signals else 0.5
        feedback_weight = min(1.5, max(0.1, mean_signal + 0.5))

        # Compute recency preference (positive feedback on recent tickets)
        recent_30d = [
            fb for fb in recent_feedback
            if fb.created_at and (now - (fb.created_at if fb.created_at.tzinfo else fb.created_at.replace(tzinfo=timezone.utc))).days <= 30
        ]
        recency_positive = sum(1 for fb in recent_30d if fb.rating >= 4)
        recency_weight = settings.reranking_recency_weight
        if recent_30d:
            recency_pos_rate = recency_positive / len(recent_30d)
            recency_weight = max(0.05, min(0.5, recency_pos_rate * 0.4))

        # Persist updated weights
        updated_weights = {
            "similarity": settings.reranking_similarity_weight,
            "recency": recency_weight,
            "feedback": feedback_weight,
            "quality": settings.reranking_quality_weight,
        }

        for feature, weight in updated_weights.items():
            await self._reranking_repo.upsert_weight(
                feature_name=feature,
                weight=weight,
                feedback_count=total_count,
                positive_count=helpful_count,
                negative_count=total_count - helpful_count,
                average_rating=sum(fb.rating for fb in recent_feedback) / total_count,
            )

        scheduler_job_runs_total.labels(
            job_name="feedback_aggregation", status="success"
        ).inc()

        logger.info(
            "Reranking weights updated: %s (samples=%d acceptance=%.2f)",
            updated_weights, total_count, acceptance_rate,
        )
        return {
            "updated": True,
            "weights": updated_weights,
            "samples_used": total_count,
            "acceptance_rate": acceptance_rate,
        }

    def _compute_feedback_signal(
        self, rating: int, was_helpful: bool, days_elapsed: float
    ) -> float:
        """Compute exponentially decayed feedback signal in [0, 1]."""
        base = (rating - 1) / 4.0  # Normalize [1,5] -> [0,1]
        helpfulness_factor = 1.0 if was_helpful else 0.4
        decay = math.exp(-self._settings.feedback_decay_lambda * days_elapsed)
        return base * helpfulness_factor * decay

    async def _maybe_trigger_aggregation(self) -> None:
        """Check if enough new feedback has accumulated to trigger weight update."""
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        recent_count = await self._feedback_repo.count_since(since)
        min_samples = self._settings.feedback_min_samples
        if recent_count >= min_samples and recent_count % min_samples == 0:
            logger.info("Auto-triggering feedback aggregation (count=%d)", recent_count)
            try:
                await self.aggregate_and_update_weights()
            except Exception as e:
                logger.error("Auto-aggregation failed: %s", e)

    async def get_stats(self) -> FeedbackStatsResponse:
        stats = await self._feedback_repo.get_global_stats()
        per_ticket = await self._feedback_repo.get_aggregated_by_ticket()
        top_rated = sorted(per_ticket, key=lambda x: x["avg_rating"], reverse=True)[:5]
        return FeedbackStatsResponse(
            total_feedback=stats["total_feedback"],
            avg_rating=stats["avg_rating"],
            helpful_count=stats["helpful_count"],
            acceptance_rate=stats["acceptance_rate"],
            top_rated_tickets=top_rated,
        )