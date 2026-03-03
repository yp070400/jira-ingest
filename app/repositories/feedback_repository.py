"""Feedback repository."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_, func as sqlfunc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feedback import FeedbackModel
from app.repositories.base import BaseRepository


class FeedbackRepository(BaseRepository[FeedbackModel]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(FeedbackModel, session)

    async def get_for_ticket(
        self, suggested_ticket_id: str, limit: int = 100
    ) -> list[FeedbackModel]:
        stmt = (
            select(FeedbackModel)
            .where(FeedbackModel.suggested_ticket_id == suggested_ticket_id)
            .order_by(FeedbackModel.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_recent(self, since: datetime, limit: int = 1000) -> list[FeedbackModel]:
        stmt = (
            select(FeedbackModel)
            .where(FeedbackModel.created_at >= since)
            .order_by(FeedbackModel.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_since(self, since: datetime) -> int:
        stmt = select(sqlfunc.count()).select_from(FeedbackModel).where(
            FeedbackModel.created_at >= since
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def get_aggregated_by_ticket(
        self, since: datetime | None = None
    ) -> list[dict]:
        """Return per-ticket aggregated feedback stats."""
        base = select(
            FeedbackModel.suggested_ticket_id,
            sqlfunc.count().label("total_feedback"),
            sqlfunc.avg(FeedbackModel.rating).label("avg_rating"),
            sqlfunc.sum(
                sqlfunc.cast(FeedbackModel.was_helpful, sqlfunc.Integer)
            ).label("helpful_count"),
            sqlfunc.sum(
                sqlfunc.cast(FeedbackModel.was_correct, sqlfunc.Integer)
            ).label("correct_count"),
        ).group_by(FeedbackModel.suggested_ticket_id)

        if since:
            base = base.where(FeedbackModel.created_at >= since)

        result = await self._session.execute(base)
        return [
            {
                "ticket_id": row.suggested_ticket_id,
                "total_feedback": row.total_feedback,
                "avg_rating": float(row.avg_rating or 0),
                "helpful_count": int(row.helpful_count or 0),
                "correct_count": int(row.correct_count or 0),
            }
            for row in result.all()
        ]

    async def get_global_stats(self) -> dict:
        stmt = select(
            sqlfunc.count().label("total"),
            sqlfunc.avg(FeedbackModel.rating).label("avg_rating"),
            sqlfunc.sum(
                sqlfunc.cast(FeedbackModel.was_helpful, sqlfunc.Integer)
            ).label("helpful_count"),
        )
        result = await self._session.execute(stmt)
        row = result.one()
        total = int(row.total or 0)
        helpful = int(row.helpful_count or 0)
        return {
            "total_feedback": total,
            "avg_rating": float(row.avg_rating or 0),
            "helpful_count": helpful,
            "acceptance_rate": (helpful / total) if total > 0 else 0.0,
        }