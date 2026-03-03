"""Embedding metadata repository."""
from __future__ import annotations

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.embedding import EmbeddingModel
from app.repositories.base import BaseRepository


class EmbeddingRepository(BaseRepository[EmbeddingModel]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(EmbeddingModel, session)

    async def get_by_ticket_id(self, ticket_id: str) -> EmbeddingModel | None:
        stmt = select(EmbeddingModel).where(EmbeddingModel.ticket_id == ticket_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_faiss_id(self, faiss_id: int) -> EmbeddingModel | None:
        stmt = select(EmbeddingModel).where(EmbeddingModel.faiss_index_id == faiss_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_for_version(self, version: str) -> list[EmbeddingModel]:
        stmt = select(EmbeddingModel).where(EmbeddingModel.vector_version == version)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_stale_embeddings(
        self, current_version: str, limit: int = 500
    ) -> list[EmbeddingModel]:
        stmt = (
            select(EmbeddingModel)
            .where(EmbeddingModel.vector_version != current_version)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def upsert_embedding(self, embedding_data: dict) -> tuple[EmbeddingModel, bool]:
        existing = await self.get_by_ticket_id(embedding_data["ticket_id"])
        if existing:
            for key, value in embedding_data.items():
                if key != "id":
                    setattr(existing, key, value)
            self._session.add(existing)
            await self._session.flush()
            return existing, False
        model = EmbeddingModel(**embedding_data)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return model, True

    async def get_all_faiss_mappings(self) -> list[tuple[str, int]]:
        """Return list of (ticket_id, faiss_index_id) for all embeddings."""
        stmt = select(EmbeddingModel.ticket_id, EmbeddingModel.faiss_index_id).where(
            EmbeddingModel.faiss_index_id.is_not(None)
        )
        result = await self._session.execute(stmt)
        return [(row.ticket_id, row.faiss_index_id) for row in result.all()]