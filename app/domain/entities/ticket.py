"""Ticket domain entity — pure Python, no ORM dependencies."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class TicketPriority(str, Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    TRIVIAL = "Trivial"
    UNKNOWN = "Unknown"


class TicketStatus(str, Enum):
    OPEN = "Open"
    IN_PROGRESS = "In Progress"
    IN_REVIEW = "In Review"
    DONE = "Done"
    RESOLVED = "Resolved"
    CLOSED = "Closed"
    WONT_FIX = "Won't Fix"


@dataclass
class TicketEntity:
    """Core domain entity representing a JIRA ticket."""

    jira_id: str
    project_key: str
    summary: str
    status: str
    priority: str = TicketPriority.UNKNOWN.value
    description: str | None = None
    resolution: str | None = None
    reporter: str | None = None
    assignee: str | None = None
    labels: list[str] = field(default_factory=list)
    components: list[str] = field(default_factory=list)
    fix_versions: list[str] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    resolved_at: datetime | None = None
    raw_data: dict[str, Any] = field(default_factory=dict)
    quality_score: float = 0.0
    embedding_version: str | None = None
    id: str | None = None

    @property
    def is_resolved(self) -> bool:
        return self.status in {
            TicketStatus.DONE.value,
            TicketStatus.RESOLVED.value,
            TicketStatus.CLOSED.value,
        }

    @property
    def searchable_text(self) -> str:
        """Combined text used for embedding generation."""
        parts = [f"Summary: {self.summary}"]
        if self.description:
            parts.append(f"Description: {self.description}")
        if self.resolution:
            parts.append(f"Resolution: {self.resolution}")
        if self.labels:
            parts.append(f"Labels: {', '.join(self.labels)}")
        if self.components:
            parts.append(f"Components: {', '.join(self.components)}")
        return "\n\n".join(parts)

    def truncate_for_embedding(self, max_chars: int = 8000) -> str:
        """Return text truncated to fit model token limits."""
        text = self.searchable_text
        if len(text) > max_chars:
            return text[:max_chars] + "..."
        return text

    def compute_quality_score(self) -> float:
        from app.domain.value_objects.score import QualityScore

        score = QualityScore.from_ticket_metadata(
            has_description=bool(self.description and len(self.description) > 50),
            has_resolution=bool(self.resolution and len(self.resolution) > 20),
            has_labels=bool(self.labels),
            has_components=bool(self.components),
            comment_count=len(self.raw_data.get("comments", [])),
        )
        self.quality_score = score.value
        return score.value