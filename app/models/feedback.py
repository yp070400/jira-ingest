"""Feedback ORM model."""
from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class FeedbackModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "feedback"

    query_ticket_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    suggested_ticket_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("jira_tickets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_version: Mapped[str] = mapped_column(String(64), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    was_helpful: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    was_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Relationships
    reviewer = relationship("UserModel", back_populates="feedback_items", lazy="noload")

    __table_args__ = (
        Index("ix_feedback_suggested_ticket", "suggested_ticket_id"),
        Index("ix_feedback_reviewer", "reviewer_id"),
        Index("ix_feedback_rating", "rating"),
    )

    def __repr__(self) -> str:
        return (
            f"<FeedbackModel query={self.query_ticket_id!r} "
            f"suggested={self.suggested_ticket_id!r} rating={self.rating}>"
        )