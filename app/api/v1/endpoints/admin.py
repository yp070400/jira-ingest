"""Admin endpoints — reindex, audit logs, system status."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_embedding_service, get_vector_store
from app.application.dto.ticket_dto import ReindexStatusResponse
from app.application.services.embedding_service import EmbeddingService
from app.infrastructure.database.session import get_db_session
from app.observability.logger import get_logger
from app.repositories.audit_repository import AuditRepository
from app.repositories.ticket_repository import TicketRepository
from app.security.rbac import CurrentUser, RequireAdmin

router = APIRouter(prefix="/admin", tags=["admin"])
logger = get_logger(__name__)


@router.post("/reindex", response_model=ReindexStatusResponse)
async def trigger_reindex(
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(RequireAdmin),
    embedding_svc: EmbeddingService = Depends(get_embedding_service),
) -> ReindexStatusResponse:
    """Trigger a full vector index rebuild. Runs asynchronously. Admin only."""
    vector_store = get_vector_store()
    current_count = vector_store.count()

    background_tasks.add_task(embedding_svc.reindex_all)
    logger.info("Reindex triggered", user=current_user.email)

    return ReindexStatusResponse(
        triggered=True,
        message="Full reindex triggered in background",
        total_indexed=current_count,
    )


@router.get("/embedding-health", response_model=dict)
async def embedding_health(
    current_user: CurrentUser = Depends(RequireAdmin),
    embedding_svc: EmbeddingService = Depends(get_embedding_service),
) -> dict:
    return await embedding_svc.get_embedding_health()


@router.get("/audit-logs", response_model=list[dict])
async def get_audit_logs(
    action: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    current_user: CurrentUser = Depends(RequireAdmin),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    audit_repo = AuditRepository(session)
    if action:
        logs = await audit_repo.get_by_action(action, limit=limit)
    else:
        logs = await audit_repo.get_all(limit=limit)
    return [
        {
            "id": log.id,
            "action": log.action,
            "user_id": log.user_id,
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "status": log.status,
            "ip_address": log.ip_address,
            "created_at": log.created_at.isoformat() if log.created_at else None,
            "details": log.details,
        }
        for log in logs
    ]


@router.get("/system-status", response_model=dict)
async def system_status(
    current_user: CurrentUser = Depends(RequireAdmin),
    session: AsyncSession = Depends(get_db_session),
    embedding_svc: EmbeddingService = Depends(get_embedding_service),
) -> dict:
    from app.adapters.llm.embedding_adapters import get_jira_adapter, get_llm_adapter
    from app.infrastructure.cache.redis_client import get_redis_client

    vector_store = get_vector_store()
    ticket_repo = TicketRepository(session)

    total_tickets = await ticket_repo.count()
    by_project = await ticket_repo.count_by_project()

    jira_ok = await get_jira_adapter().health_check()
    llm_ok = await get_llm_adapter().health_check()
    redis_ok = await get_redis_client().ping()
    embedding_health = await embedding_svc.get_embedding_health()

    return {
        "database": {"status": "ok", "total_tickets": total_tickets, "by_project": by_project},
        "vector_store": {"status": "ok", "indexed_count": vector_store.count()},
        "redis": {"status": "ok" if redis_ok else "error"},
        "jira": {"status": "ok" if jira_ok else "error"},
        "llm": {"status": "ok" if llm_ok else "error"},
        "embedding": embedding_health,
    }