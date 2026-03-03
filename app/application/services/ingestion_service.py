"""JIRA ticket ingestion service."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.config import get_settings
from app.domain.interfaces.jira_port import JiraPort
from app.observability.metrics import (
    ingestion_errors_total,
    scheduler_job_runs_total,
    tickets_ingested_total,
)

if TYPE_CHECKING:
    from app.application.services.embedding_service import EmbeddingService
    from app.repositories.ticket_repository import TicketRepository

logger = logging.getLogger(__name__)


class IngestionService:
    """Ingests JIRA tickets from configured projects."""

    def __init__(
        self,
        jira_adapter: JiraPort,
        ticket_repo: "TicketRepository",
        embedding_service: "EmbeddingService",
    ) -> None:
        self._jira = jira_adapter
        self._ticket_repo = ticket_repo
        self._embedding_service = embedding_service
        self._settings = get_settings()

    async def sync_all_projects(self, incremental: bool = True) -> dict:
        """Sync all configured projects. Returns summary stats."""
        project_keys = self._settings.jira_project_keys_list
        resolved_statuses = self._settings.jira_resolved_statuses_list

        total_new = 0
        total_updated = 0
        total_indexed = 0
        errors: list[str] = []

        for project_key in project_keys:
            try:
                stats = await self._sync_project(
                    project_key, resolved_statuses, incremental=incremental
                )
                total_new += stats["new"]
                total_updated += stats["updated"]
                total_indexed += stats["indexed"]
            except Exception as e:
                error_msg = f"{project_key}: {e}"
                errors.append(error_msg)
                logger.error("Ingestion failed for project %s: %s", project_key, e)
                ingestion_errors_total.labels(error_type=type(e).__name__).inc()

        scheduler_job_runs_total.labels(
            job_name="jira_sync",
            status="success" if not errors else "partial",
        ).inc()

        return {
            "projects_synced": len(project_keys),
            "new_tickets": total_new,
            "updated_tickets": total_updated,
            "newly_indexed": total_indexed,
            "errors": errors,
            "sync_time": datetime.now(timezone.utc).isoformat(),
        }

    async def _sync_project(
        self,
        project_key: str,
        resolved_statuses: list[str],
        incremental: bool = True,
    ) -> dict:
        """Sync a single project. Returns {new, updated, indexed}."""
        since = None
        if incremental:
            since = await self._ticket_repo.get_last_sync_time(project_key)

        logger.info(
            "Syncing project=%s since=%s incremental=%s",
            project_key, since, incremental,
        )

        tickets = await self._jira.fetch_resolved_tickets(
            project_keys=[project_key],
            resolved_statuses=resolved_statuses,
            since=since,
            max_results=self._settings.jira_max_results_per_page * 5,
        )

        new_count = 0
        updated_count = 0
        indexed_count = 0

        for ticket in tickets:
            ticket_data = {
                "jira_id": ticket.jira_id,
                "project_key": ticket.project_key,
                "summary": ticket.summary,
                "description": ticket.description,
                "status": ticket.status,
                "resolution": ticket.resolution,
                "priority": ticket.priority,
                "reporter": ticket.reporter,
                "assignee": ticket.assignee,
                "labels": ticket.labels,
                "components": ticket.components,
                "fix_versions": ticket.fix_versions,
                "raw_data": ticket.raw_data,
                "quality_score": ticket.quality_score,
                "jira_created_at": ticket.created_at,
                "jira_updated_at": ticket.updated_at,
                "resolved_at": ticket.resolved_at,
                "is_indexed": False,
            }

            try:
                model, is_new = await self._ticket_repo.upsert_ticket(ticket_data)
                if is_new:
                    new_count += 1
                    tickets_ingested_total.labels(
                        project_key=project_key, is_new="true"
                    ).inc()
                else:
                    updated_count += 1
                    tickets_ingested_total.labels(
                        project_key=project_key, is_new="false"
                    ).inc()

                # Only index high-quality tickets
                if ticket.quality_score >= 0.3:
                    faiss_id = await self._embedding_service.embed_and_index_ticket(model.id)
                    if faiss_id is not None:
                        indexed_count += 1

            except Exception as e:
                logger.warning(
                    "Failed to upsert ticket %s: %s", ticket.jira_id, e
                )
                ingestion_errors_total.labels(error_type="upsert_error").inc()

        await self._embedding_service._vector_store.persist()

        logger.info(
            "Project %s sync complete: new=%d updated=%d indexed=%d",
            project_key, new_count, updated_count, indexed_count,
        )
        return {"new": new_count, "updated": updated_count, "indexed": indexed_count}

    async def sync_single_ticket(self, jira_id: str) -> dict | None:
        """Fetch and upsert a single ticket by JIRA ID."""
        ticket = await self._jira.fetch_ticket_by_id(jira_id)
        if not ticket:
            return None

        ticket_data = {
            "jira_id": ticket.jira_id,
            "project_key": ticket.project_key,
            "summary": ticket.summary,
            "description": ticket.description,
            "status": ticket.status,
            "resolution": ticket.resolution,
            "priority": ticket.priority,
            "reporter": ticket.reporter,
            "assignee": ticket.assignee,
            "labels": ticket.labels,
            "components": ticket.components,
            "fix_versions": ticket.fix_versions,
            "raw_data": ticket.raw_data,
            "quality_score": ticket.quality_score,
            "jira_created_at": ticket.created_at,
            "jira_updated_at": ticket.updated_at,
            "resolved_at": ticket.resolved_at,
            "is_indexed": False,
        }

        model, is_new = await self._ticket_repo.upsert_ticket(ticket_data)
        if ticket.quality_score >= 0.3:
            await self._embedding_service.embed_and_index_ticket(model.id)
            await self._embedding_service._vector_store.persist()

        return {"jira_id": jira_id, "is_new": is_new, "db_id": model.id}