"""User repository."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import UserModel
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[UserModel]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(UserModel, session)

    async def get_by_email(self, email: str) -> UserModel | None:
        stmt = select(UserModel).where(UserModel.email == email)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_by_email(self, email: str) -> UserModel | None:
        stmt = select(UserModel).where(
            UserModel.email == email, UserModel.is_active.is_(True)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_last_login(self, user_id: str) -> None:
        stmt = (
            update(UserModel)
            .where(UserModel.id == user_id)
            .values(last_login_at=datetime.utcnow())
        )
        await self._session.execute(stmt)

    async def deactivate(self, user_id: str) -> None:
        stmt = (
            update(UserModel)
            .where(UserModel.id == user_id)
            .values(is_active=False)
        )
        await self._session.execute(stmt)

    async def list_by_role(self, role: str, limit: int = 100) -> list[UserModel]:
        stmt = (
            select(UserModel)
            .where(UserModel.role == role, UserModel.is_active.is_(True))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())