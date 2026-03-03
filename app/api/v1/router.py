"""V1 API router — aggregates all endpoint routers."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints.admin import router as admin_router
from app.api.v1.endpoints.analyze import router as analyze_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.feedback import router as feedback_router
from app.api.v1.endpoints.tickets import router as tickets_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth_router)
api_router.include_router(tickets_router)
api_router.include_router(analyze_router)
api_router.include_router(feedback_router)
api_router.include_router(admin_router)