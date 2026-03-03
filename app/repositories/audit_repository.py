"""Audit log repository."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLogModel
from app.repositories.base import BaseRepository


class AuditRepository(BaseRepository[AuditLogModel]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(AuditLogModel, session)

    async def log(
        self,
        action: str,
        user_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        details: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        status: str = "success",
        error_message: str | None = None,
    ) -> AuditLogModel:
        entry = AuditLogModel(
            action=action,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            status=status,
            error_message=error_message,
        )
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def get_by_user(
        self,
        user_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLogModel]:
        stmt = (
            select(AuditLogModel)
            .where(AuditLogModel.user_id == user_id)
            .order_by(AuditLogModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_action(
        self,
        action: str,
        since: datetime | None = None,
        limit: int = 200,
    ) -> list[AuditLogModel]:
        stmt = select(AuditLogModel).where(AuditLogModel.action == action)
        if since:
            stmt = stmt.where(AuditLogModel.created_at >= since)
        stmt = stmt.order_by(AuditLogModel.created_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_failures(self, limit: int = 100) -> list[AuditLogModel]:
        stmt = (
            select(AuditLogModel)
            .where(AuditLogModel.status == "failure")
            .order_by(AuditLogModel.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())