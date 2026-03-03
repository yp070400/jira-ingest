"""Analysis endpoints — Quick and Deep modes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_analysis_service
from app.application.dto.analysis_dto import (
    AnalysisMode,
    AnalysisRequest,
    DeepAnalysisResponse,
    QuickAnalysisResponse,
)
from app.application.services.analysis_service import AnalysisService
from app.domain.exceptions.domain_exceptions import (
    EmbeddingGenerationError,
    LLMError,
    VectorIndexError,
)
from app.infrastructure.database.session import get_db_session
from app.observability.logger import get_logger
from app.security.rate_limiter import deep_analysis_rate_limit, rate_limit
from app.security.rbac import CurrentUser, get_current_user

router = APIRouter(prefix="/analyze", tags=["analysis"])
logger = get_logger(__name__)


@router.post(
    "",
    response_model=QuickAnalysisResponse | DeepAnalysisResponse,
    summary="Analyze a ticket for resolution intelligence",
)
async def analyze(
    request: Request,
    body: AnalysisRequest,
    current_user: CurrentUser = Depends(get_current_user),
    analysis_svc: AnalysisService = Depends(get_analysis_service),
    _rate_limit=Depends(rate_limit(key="analyze")),
) -> QuickAnalysisResponse | DeepAnalysisResponse:
    """
    Analyze a JIRA ticket and return resolution suggestions.

    **Quick mode** (default):
    - 3-5 line fix summary + similarity/confidence scores
    - Cached for 30 minutes — target: < 1.5s

    **Deep mode** (requires Reviewer/Admin role):
    - Root cause, risk assessment, step-by-step fix
    - Related JIRAs — target: < 5s
    """
    if body.mode == AnalysisMode.DEEP:
        if not current_user.has_permission("analyze:deep"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Deep analysis requires Reviewer or Admin role",
            )
        await deep_analysis_rate_limit()(request)

    ip = request.client.host if request.client else None

    try:
        result = await analysis_svc.analyze(
            text=body.text,
            mode=body.mode,
            jira_id=body.jira_id,
            project_key=body.project_key,
            user_id=current_user.user_id,
            ip_address=ip,
        )
    except EmbeddingGenerationError as e:
        logger.error("Embedding generation failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Embedding service unavailable",
        ) from e
    except LLMError as e:
        logger.error("LLM request failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM service unavailable",
        ) from e
    except VectorIndexError as e:
        logger.error("Vector index error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vector search unavailable",
        ) from e
    except Exception as e:
        logger.exception("Unexpected analysis error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Analysis failed",
        ) from e

    return result