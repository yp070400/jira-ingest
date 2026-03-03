"""RBAC permission enforcement for FastAPI dependencies."""
from __future__ import annotations

from functools import wraps

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.domain.entities.user import ROLE_PERMISSIONS, UserRole
from app.domain.exceptions.domain_exceptions import (
    InsufficientPermissionsError,
    InvalidCredentialsError,
)
from app.security.jwt_handler import decode_token

_bearer_scheme = HTTPBearer(auto_error=False)


class CurrentUser:
    """Resolved user context from a validated JWT."""

    def __init__(self, user_id: str, email: str, role: UserRole) -> None:
        self.user_id = user_id
        self.email = email
        self.role = role

    def has_permission(self, permission: str) -> bool:
        return permission in ROLE_PERMISSIONS.get(self.role, set())

    def require_permission(self, permission: str) -> None:
        if not self.has_permission(permission):
            raise InsufficientPermissionsError(permission)

    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    def is_reviewer_or_above(self) -> bool:
        return self.role in (UserRole.REVIEWER, UserRole.ADMIN)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(credentials.credentials)
        user_id: str = payload.get("sub", "")
        email: str = payload.get("email", user_id)
        role_str: str = payload.get("role", "user")
        token_type: str = payload.get("type", "access")

        if token_type != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh tokens cannot be used for API access",
            )
        try:
            role = UserRole(role_str)
        except ValueError:
            role = UserRole.USER

        return CurrentUser(user_id=user_id, email=email, role=role)

    except InvalidCredentialsError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


def require_permission(permission: str):
    """FastAPI dependency factory for permission-based access control."""

    async def _check(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not current_user.has_permission(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: '{permission}' required",
            )
        return current_user

    return _check


def require_role(*roles: UserRole):
    """FastAPI dependency factory for role-based access control."""

    async def _check(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role required: {[r.value for r in roles]}",
            )
        return current_user

    return _check


# Pre-built dependency shortcuts
RequireUser = require_permission("tickets:read")
RequireReviewer = require_permission("analyze:deep")
RequireAdmin = require_role(UserRole.ADMIN)
RequireDeepAnalysis = require_permission("analyze:deep")