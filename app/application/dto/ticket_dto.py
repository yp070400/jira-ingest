"""Ticket DTOs for API input/output."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TicketResponse(BaseModel):
    id: str
    jira_id: str
    project_key: str
    summary: str
    description: str | None = None
    status: str
    resolution: str | None = None
    priority: str
    reporter: str | None = None
    assignee: str | None = None
    labels: list[str] = Field(default_factory=list)
    components: list[str] = Field(default_factory=list)
    quality_score: float
    is_indexed: bool
    embedding_version: str | None = None
    resolved_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class TicketListResponse(BaseModel):
    items: list[TicketResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class SyncStatusResponse(BaseModel):
    triggered: bool
    message: str
    project_keys: list[str]
    triggered_at: datetime = Field(default_factory=datetime.utcnow)


class ReindexStatusResponse(BaseModel):
    triggered: bool
    message: str
    total_indexed: int
    triggered_at: datetime = Field(default_factory=datetime.utcnow)