"""Abstract JIRA port — defines the contract for JIRA adapters."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from app.domain.entities.ticket import TicketEntity


class JiraPort(ABC):
    """Port (interface) for JIRA data source adapters."""

    @abstractmethod
    async def fetch_resolved_tickets(
        self,
        project_keys: list[str],
        resolved_statuses: list[str],
        since: datetime | None = None,
        max_results: int = 100,
    ) -> list[TicketEntity]:
        """Fetch resolved/done tickets from JIRA."""

    @abstractmethod
    async def fetch_ticket_by_id(self, jira_id: str) -> TicketEntity | None:
        """Fetch a single ticket by its JIRA ID."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Verify connectivity to the JIRA instance."""

    @abstractmethod
    async def get_total_count(
        self,
        project_keys: list[str],
        resolved_statuses: list[str],
        since: datetime | None = None,
    ) -> int:
        """Get total count of matching tickets (for progress tracking)."""