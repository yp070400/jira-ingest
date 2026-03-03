"""User domain entity."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class UserRole(str, Enum):
    USER = "user"
    REVIEWER = "reviewer"
    ADMIN = "admin"


# Permission matrix
ROLE_PERMISSIONS: dict[UserRole, set[str]] = {
    UserRole.USER: {
        "analyze:quick",
        "tickets:read",
        "feedback:write",
        "health:read",
    },
    UserRole.REVIEWER: {
        "analyze:quick",
        "analyze:deep",
        "tickets:read",
        "tickets:write",
        "feedback:write",
        "feedback:read",
        "health:read",
    },
    UserRole.ADMIN: {
        "analyze:quick",
        "analyze:deep",
        "tickets:read",
        "tickets:write",
        "tickets:sync",
        "feedback:write",
        "feedback:read",
        "feedback:admin",
        "admin:users",
        "admin:reindex",
        "admin:weights",
        "admin:metrics",
        "health:read",
    },
}


@dataclass
class UserEntity:
    """Core domain entity representing a platform user."""

    email: str
    role: UserRole
    hashed_password: str
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_login_at: datetime | None = None
    id: str | None = None

    def has_permission(self, permission: str) -> bool:
        return permission in ROLE_PERMISSIONS.get(self.role, set())

    def can_access_deep_analysis(self) -> bool:
        return self.has_permission("analyze:deep")

    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    def is_reviewer_or_above(self) -> bool:
        return self.role in (UserRole.REVIEWER, UserRole.ADMIN)