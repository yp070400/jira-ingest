"""Audit log ORM model."""
from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base, UUIDPrimaryKeyMixin
from sqlalchemy import DateTime
from sqlalchemy.sql import func
from datetime import datetime


class AuditLogModel(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "audit_logs"

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="success"
    )  # "success" | "failure"
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    user = relationship("UserModel", back_populates="audit_logs", lazy="noload")

    __table_args__ = (
        Index("ix_audit_logs_action_status", "action", "status"),
        Index("ix_audit_logs_user_action", "user_id", "action"),
        Index("ix_audit_logs_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLogModel action={self.action!r} "
            f"user_id={self.user_id!r} status={self.status!r}>"
        )