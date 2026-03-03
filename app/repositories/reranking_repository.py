"""Reranking weights repository."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reranking import RerankingWeightModel
from app.repositories.base import BaseRepository


class RerankingRepository(BaseRepository[RerankingWeightModel]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(RerankingWeightModel, session)

    async def get_by_feature(self, feature_name: str) -> RerankingWeightModel | None:
        stmt = select(RerankingWeightModel).where(
            RerankingWeightModel.feature_name == feature_name
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_weights(self) -> dict[str, float]:
        stmt = select(RerankingWeightModel)
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return {row.feature_name: row.weight for row in rows}

    async def upsert_weight(
        self,
        feature_name: str,
        weight: float,
        feedback_count: int = 0,
        positive_count: int = 0,
        negative_count: int = 0,
        average_rating: float = 0.0,
    ) -> RerankingWeightModel:
        existing = await self.get_by_feature(feature_name)
        if existing:
            existing.weight = weight
            existing.feedback_count = feedback_count
            existing.positive_count = positive_count
            existing.negative_count = negative_count
            existing.average_rating = average_rating
            self._session.add(existing)
            await self._session.flush()
            return existing
        model = RerankingWeightModel(
            feature_name=feature_name,
            weight=weight,
            feedback_count=feedback_count,
            positive_count=positive_count,
            negative_count=negative_count,
            average_rating=average_rating,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return model