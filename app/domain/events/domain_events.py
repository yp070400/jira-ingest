"""Domain events for cross-cutting communication."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


@dataclass
class DomainEvent:
    event_id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TicketIngestedEvent(DomainEvent):
    jira_id: str = ""
    project_key: str = ""
    is_new: bool = True


@dataclass
class EmbeddingGeneratedEvent(DomainEvent):
    ticket_id: str = ""
    vector_version: str = ""
    model_name: str = ""


@dataclass
class AnalysisRequestedEvent(DomainEvent):
    mode: str = "quick"
    query_text: str = ""
    user_id: str = ""
    ip_address: str = ""


@dataclass
class FeedbackSubmittedEvent(DomainEvent):
    feedback_id: str = ""
    suggested_ticket_id: str = ""
    rating: int = 0
    was_helpful: bool = False


@dataclass
class ReviewFlaggedEvent(DomainEvent):
    query_text: str = ""
    reason: str = ""
    confidence: float = 0.0
    user_id: str = ""


@dataclass
class ReindexRequestedEvent(DomainEvent):
    requested_by: str = ""
    reason: str = ""