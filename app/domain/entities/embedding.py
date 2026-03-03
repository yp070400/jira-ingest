"""Embedding domain entity."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class EmbeddingEntity:
    """Metadata record for a stored ticket embedding."""

    ticket_id: str
    vector_version: str
    model_name: str
    embedding_dimension: int
    embedding_hash: str  # SHA-256 of the raw vector for dedup detection
    faiss_index_id: int | None = None
    created_at: datetime | None = None
    id: str | None = None

    def is_stale(self, current_version: str) -> bool:
        return self.vector_version != current_version