"""Reranking weights ORM model."""
from __future__ import annotations

from sqlalchemy import Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class RerankingWeightModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "reranking_weights"

    feature_name: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    feedback_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    positive_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    negative_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    average_rating: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    last_recalibrated_version: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )

    __table_args__ = (
        Index("ix_reranking_weights_feature", "feature_name"),
    )

    def __repr__(self) -> str:
        return (
            f"<RerankingWeightModel feature={self.feature_name!r} "
            f"weight={self.weight:.4f} feedback_count={self.feedback_count}>"
        )