"""Embedding metadata ORM model."""
from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class EmbeddingModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "embeddings"

    ticket_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("jira_tickets.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    vector_version: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    faiss_index_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)

    # Relationships
    ticket = relationship("JiraTicketModel", back_populates="embedding", lazy="noload")

    __table_args__ = (
        Index("ix_embeddings_version_model", "vector_version", "model_name"),
    )

    def __repr__(self) -> str:
        return (
            f"<EmbeddingModel ticket_id={self.ticket_id!r} "
            f"version={self.vector_version!r} faiss_id={self.faiss_index_id!r}>"
        )