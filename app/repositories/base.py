"""Generic async repository base class."""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Generic CRUD repository with async SQLAlchemy."""

    def __init__(self, model: type[ModelType], session: AsyncSession) -> None:
        self._model = model
        self._session = session

    async def get_by_id(self, id: str) -> ModelType | None:
        result = await self._session.get(self._model, id)
        return result

    async def get_all(self, limit: int = 100, offset: int = 0) -> list[ModelType]:
        stmt = select(self._model).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, obj: ModelType) -> ModelType:
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj)
        return obj

    async def update(self, obj: ModelType, **kwargs: Any) -> ModelType:
        for key, value in kwargs.items():
            setattr(obj, key, value)
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj)
        return obj

    async def delete(self, obj: ModelType) -> None:
        await self._session.delete(obj)
        await self._session.flush()

    async def count(self) -> int:
        from sqlalchemy import func as sqlfunc

        stmt = select(sqlfunc.count()).select_from(self._model)
        result = await self._session.execute(stmt)
        return result.scalar_one()