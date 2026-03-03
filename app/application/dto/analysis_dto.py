"""Analysis request and response DTOs."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class AnalysisMode(str, Enum):
    QUICK = "quick"
    DEEP = "deep"


class AnalysisRequest(BaseModel):
    text: str = Field(..., min_length=10, max_length=10000, description="Ticket text to analyze")
    mode: AnalysisMode = Field(AnalysisMode.QUICK, description="Analysis depth")
    jira_id: str | None = Field(None, description="Optional reference JIRA ID")
    project_key: str | None = Field(None, description="Optional project filter")

    @field_validator("text")
    @classmethod
    def sanitize_text(cls, v: str) -> str:
        return v.strip()


class SimilarTicketDTO(BaseModel):
    jira_id: str
    ticket_db_id: str
    summary: str
    resolution: str | None = None
    similarity_score: float
    confidence_score: float
    project_key: str
    priority: str
    resolved_at: datetime | None = None
    labels: list[str] = Field(default_factory=list)
    components: list[str] = Field(default_factory=list)
    quality_score: float = 0.0


class QuickAnalysisResponse(BaseModel):
    mode: str = "quick"
    jira_id: str | None = None
    fix_summary: str
    fix_suggestion: str
    similar_tickets: list[SimilarTicketDTO]
    top_similarity_score: float
    confidence_score: float
    confidence_label: str
    requires_human_review: bool
    review_reasons: list[str] = Field(default_factory=list)
    model_version: str
    embedding_version: str
    cache_hit: bool = False
    processed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    processing_time_ms: float = 0.0


class DeepAnalysisResponse(BaseModel):
    mode: str = "deep"
    jira_id: str | None = None
    root_cause: str
    resolution_reasoning: str
    risk_notes: str
    step_by_step_fix: list[str]
    related_patterns: list[str]
    related_jira_ids: list[str]
    similar_tickets: list[SimilarTicketDTO]
    top_similarity_score: float
    confidence_score: float
    confidence_label: str
    confidence_explanation: str
    requires_human_review: bool
    review_reasons: list[str] = Field(default_factory=list)
    model_version: str
    embedding_version: str
    processed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    processing_time_ms: float = 0.0