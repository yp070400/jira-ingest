"""JIRA Ticket repository."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket import JiraTicketModel
from app.repositories.base import BaseRepository


class TicketRepository(BaseRepository[JiraTicketModel]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(JiraTicketModel, session)

    async def get_by_jira_id(self, jira_id: str) -> JiraTicketModel | None:
        stmt = select(JiraTicketModel).where(JiraTicketModel.jira_id == jira_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_unindexed(self, limit: int = 500) -> list[JiraTicketModel]:
        stmt = (
            select(JiraTicketModel)
            .where(JiraTicketModel.is_indexed.is_(False))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_project(
        self, project_key: str, limit: int = 100, offset: int = 0
    ) -> list[JiraTicketModel]:
        stmt = (
            select(JiraTicketModel)
            .where(JiraTicketModel.project_key == project_key)
            .order_by(JiraTicketModel.resolved_at.desc().nullslast())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_ids(self, ids: list[str]) -> list[JiraTicketModel]:
        stmt = select(JiraTicketModel).where(JiraTicketModel.id.in_(ids))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def upsert_ticket(self, ticket_data: dict) -> tuple[JiraTicketModel, bool]:
        """Upsert a ticket. Returns (model, is_new).

        For existing tickets the is_indexed / embedding_version fields are
        preserved so that a re-ingest doesn't silently discard prior indexing
        work.  The embedding service is responsible for resetting is_indexed
        when content actually changes.
        """
        existing = await self.get_by_jira_id(ticket_data["jira_id"])
        if existing:
            skip_keys = {"id", "is_indexed", "embedding_version"}
            for key, value in ticket_data.items():
                if key not in skip_keys:
                    setattr(existing, key, value)
            self._session.add(existing)
            await self._session.flush()
            return existing, False
        else:
            model = JiraTicketModel(**ticket_data)
            self._session.add(model)
            await self._session.flush()
            await self._session.refresh(model)
            return model, True

    async def mark_as_indexed(self, ticket_id: str, embedding_version: str) -> None:
        stmt = (
            update(JiraTicketModel)
            .where(JiraTicketModel.id == ticket_id)
            .values(is_indexed=True, embedding_version=embedding_version)
        )
        await self._session.execute(stmt)

    async def get_tickets_needing_reindex(
        self, current_version: str, limit: int = 500
    ) -> list[JiraTicketModel]:
        stmt = (
            select(JiraTicketModel)
            .where(
                and_(
                    JiraTicketModel.embedding_version != current_version,
                    JiraTicketModel.is_indexed.is_(True),
                )
            )
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_last_sync_time(self, project_key: str) -> datetime | None:
        stmt = (
            select(JiraTicketModel.updated_at)
            .where(JiraTicketModel.project_key == project_key)
            .order_by(JiraTicketModel.updated_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return row

    async def search_by_text(self, query: str, limit: int = 20) -> list[JiraTicketModel]:
        from sqlalchemy import or_

        stmt = (
            select(JiraTicketModel)
            .where(
                or_(
                    JiraTicketModel.summary.ilike(f"%{query}%"),
                    JiraTicketModel.description.ilike(f"%{query}%"),
                )
            )
            .order_by(JiraTicketModel.quality_score.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_project(self) -> dict[str, int]:
        from sqlalchemy import func as sqlfunc

        stmt = select(
            JiraTicketModel.project_key,
            sqlfunc.count().label("count"),
        ).group_by(JiraTicketModel.project_key)
        result = await self._session.execute(stmt)
        return {row.project_key: row.count for row in result.all()}