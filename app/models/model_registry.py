"""Model registry ORM model — tracks active embedding/LLM model versions."""
from __future__ import annotations

from sqlalchemy import Boolean, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ModelRegistryModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "model_registry"

    model_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    model_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # "embedding" | "llm"
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)
    notes: Mapped[str | None] = mapped_column(String(512), nullable=True)

    __table_args__ = (
        Index("ix_model_registry_type_active", "model_type", "is_active"),
        Index("ix_model_registry_name_version", "model_name", "version"),
    )

    def __repr__(self) -> str:
        return (
            f"<ModelRegistryModel name={self.model_name!r} "
            f"type={self.model_type!r} version={self.version!r} active={self.is_active}>"
        )