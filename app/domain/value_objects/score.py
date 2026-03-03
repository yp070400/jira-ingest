"""Immutable value objects for scoring primitives."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SimilarityScore:
    """Cosine similarity score in [0.0, 1.0]."""

    value: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.value <= 1.0:
            raise ValueError(f"SimilarityScore must be in [0, 1], got {self.value}")

    @classmethod
    def zero(cls) -> "SimilarityScore":
        return cls(0.0)

    @classmethod
    def perfect(cls) -> "SimilarityScore":
        return cls(1.0)

    def is_above_threshold(self, threshold: float) -> bool:
        return self.value >= threshold

    def __float__(self) -> float:
        return self.value

    def __repr__(self) -> str:
        return f"SimilarityScore({self.value:.4f})"


@dataclass(frozen=True)
class ConfidenceScore:
    """Calibrated confidence score in [0.0, 1.0]."""

    value: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.value <= 1.0:
            raise ValueError(f"ConfidenceScore must be in [0, 1], got {self.value}")

    @classmethod
    def low(cls) -> "ConfidenceScore":
        return cls(0.3)

    @classmethod
    def medium(cls) -> "ConfidenceScore":
        return cls(0.6)

    @classmethod
    def high(cls) -> "ConfidenceScore":
        return cls(0.9)

    def requires_review(self, threshold: float) -> bool:
        return self.value < threshold

    def label(self) -> str:
        if self.value >= 0.85:
            return "HIGH"
        elif self.value >= 0.65:
            return "MEDIUM"
        elif self.value >= 0.45:
            return "LOW"
        return "VERY_LOW"

    def __float__(self) -> float:
        return self.value

    def __repr__(self) -> str:
        return f"ConfidenceScore({self.value:.4f})"


@dataclass(frozen=True)
class QualityScore:
    """Resolution quality score in [0.0, 1.0] derived from ticket metadata."""

    value: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.value <= 1.0:
            raise ValueError(f"QualityScore must be in [0, 1], got {self.value}")

    @classmethod
    def from_ticket_metadata(
        cls,
        has_description: bool,
        has_resolution: bool,
        has_labels: bool,
        has_components: bool,
        comment_count: int,
    ) -> "QualityScore":
        score = 0.0
        if has_description:
            score += 0.3
        if has_resolution:
            score += 0.3
        if has_labels:
            score += 0.15
        if has_components:
            score += 0.15
        score += min(0.1, comment_count * 0.02)
        return cls(min(1.0, score))

    def __float__(self) -> float:
        return self.value