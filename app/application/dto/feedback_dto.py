"""Feedback DTOs."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class FeedbackRequest(BaseModel):
    query_ticket_id: str = Field(..., description="Original ticket ID that was queried")
    suggested_ticket_id: str = Field(..., description="DB ID of the suggested ticket")
    similarity_score: float = Field(..., ge=0.0, le=1.0)
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    model_version: str
    embedding_version: str
    rating: int = Field(..., ge=1, le=5, description="Rating 1-5")
    was_helpful: bool
    was_correct: bool
    notes: str | None = Field(None, max_length=1000)


class FeedbackResponse(BaseModel):
    id: str
    query_ticket_id: str
    suggested_ticket_id: str | None
    rating: int
    was_helpful: bool
    was_correct: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class FeedbackStatsResponse(BaseModel):
    total_feedback: int
    avg_rating: float
    helpful_count: int
    acceptance_rate: float
    top_rated_tickets: list[dict[str, Any]] = Field(default_factory=list)


class WeightsResponse(BaseModel):
    weights: dict[str, float]
    last_updated: datetime | None = None
    feedback_count: int = 0