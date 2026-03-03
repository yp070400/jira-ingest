"""Ticket management endpoints."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_ingestion_service
from app.application.dto.ticket_dto import (
    SyncStatusResponse,
    TicketListResponse,
    TicketResponse,
)
from app.application.services.ingestion_service import IngestionService
from app.infrastructure.database.session import get_db_session
from app.observability.logger import get_logger
from app.repositories.ticket_repository import TicketRepository
from app.security.rbac import CurrentUser, RequireAdmin, RequireUser, get_current_user

router = APIRouter(prefix="/tickets", tags=["tickets"])
logger = get_logger(__name__)


@router.get("", response_model=TicketListResponse)
async def list_tickets(
    project_key: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(RequireUser),
    session: AsyncSession = Depends(get_db_session),
) -> TicketListResponse:
    ticket_repo = TicketRepository(session)
    offset = (page - 1) * page_size

    if project_key:
        tickets = await ticket_repo.get_by_project(project_key, limit=page_size, offset=offset)
        total = len(tickets)
    else:
        tickets = await ticket_repo.get_all(limit=page_size, offset=offset)
        total = await ticket_repo.count()

    return TicketListResponse(
        items=[TicketResponse.model_validate(t) for t in tickets],
        total=total,
        page=page,
        page_size=page_size,
        has_next=(offset + page_size) < total,
    )


@router.get("/stats/by-project", response_model=dict)
async def stats_by_project(
    current_user: CurrentUser = Depends(RequireUser),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    ticket_repo = TicketRepository(session)
    return await ticket_repo.count_by_project()


@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_ticket(
    ticket_id: str,
    current_user: CurrentUser = Depends(RequireUser),
    session: AsyncSession = Depends(get_db_session),
) -> TicketResponse:
    ticket_repo = TicketRepository(session)
    ticket = await ticket_repo.get_by_id(ticket_id) or await ticket_repo.get_by_jira_id(ticket_id)
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    return TicketResponse.model_validate(ticket)


@router.post("/sync", response_model=SyncStatusResponse)
async def trigger_sync(
    background_tasks: BackgroundTasks,
    incremental: bool = Query(True),
    current_user: CurrentUser = Depends(RequireAdmin),
    ingestion_svc: IngestionService = Depends(get_ingestion_service),
) -> SyncStatusResponse:
    """Manually trigger JIRA sync. Admin only. Runs in background."""
    from app.config import get_settings
    settings = get_settings()

    background_tasks.add_task(ingestion_svc.sync_all_projects, incremental=incremental)
    logger.info("Manual sync triggered", user=current_user.email, incremental=incremental)

    return SyncStatusResponse(
        triggered=True,
        message=f"{'Incremental' if incremental else 'Full'} sync triggered in background",
        project_keys=settings.jira_project_keys_list,
    )


@router.post("/sync/{jira_id}", response_model=dict)
async def sync_single_ticket(
    jira_id: str,
    current_user: CurrentUser = Depends(RequireAdmin),
    ingestion_svc: IngestionService = Depends(get_ingestion_service),
) -> dict:
    result = await ingestion_svc.sync_single_ticket(jira_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket '{jira_id}' not found in JIRA",
        )
    return result