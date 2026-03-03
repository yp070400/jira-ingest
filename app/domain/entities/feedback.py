"""Feedback domain entity."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class FeedbackEntity:
    """Domain entity representing user feedback on a suggestion."""

    query_ticket_id: str
    suggested_ticket_id: str
    similarity_score: float
    confidence_score: float
    model_version: str
    embedding_version: str
    rating: int  # 1–5
    was_helpful: bool
    was_correct: bool
    reviewer_id: str
    created_at: datetime | None = None
    notes: str | None = None
    id: str | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.rating <= 5:
            raise ValueError(f"Rating must be between 1 and 5, got {self.rating}")

    @property
    def is_positive(self) -> bool:
        return self.rating >= 4 and self.was_helpful

    @property
    def normalized_rating(self) -> float:
        """Normalize rating from [1, 5] to [0, 1]."""
        return (self.rating - 1) / 4.0

    def to_reranking_signal(self, decay_lambda: float, days_elapsed: float) -> float:
        """Compute decayed reranking signal for this feedback item."""
        import math

        base_signal = self.normalized_rating * (1.0 if self.was_helpful else 0.3)
        decay = math.exp(-decay_lambda * days_elapsed)
        return base_signal * decay