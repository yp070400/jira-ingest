"""JIRA Ticket ORM model."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class JiraTicketModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "jira_tickets"

    jira_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    project_key: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(String(1024), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(String(32), nullable=False, default="Unknown")
    reporter: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assignee: Mapped[str | None] = mapped_column(String(255), nullable=True)
    labels: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=list)
    components: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=list)
    fix_versions: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=list)
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    embedding_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    jira_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    jira_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    is_indexed: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Relationships
    embedding = relationship(
        "EmbeddingModel",
        back_populates="ticket",
        uselist=False,
        lazy="noload",
    )

    __table_args__ = (
        Index("ix_tickets_project_status", "project_key", "status"),
        Index("ix_tickets_embedding_version", "embedding_version"),
        Index("ix_tickets_is_indexed", "is_indexed"),
        Index("ix_tickets_quality_score", "quality_score"),
    )

    def __repr__(self) -> str:
        return f"<JiraTicketModel jira_id={self.jira_id!r} status={self.status!r}>"